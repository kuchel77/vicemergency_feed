
"""Support for VICEmergency Feeds."""
from datetime import timedelta
import logging
from typing import Optional

from aio_geojson_vicemergency_incidents import VICEmergencyIncidentsFeedManager
import voluptuous as vol

from homeassistant.components.geo_location import PLATFORM_SCHEMA, GeolocationEvent
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_LOCATION,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_RADIUS,
    CONF_SCAN_INTERVAL,
    EVENT_HOMEASSISTANT_START,
    EVENT_HOMEASSISTANT_STOP,
    LENGTH_KILOMETERS,
)
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client, config_validation as cv
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

_LOGGER = logging.getLogger(__name__)

ATTR_CATEGORY1 = "category1"
ATTR_CATEGORY2 = "category2"
ATTR_DESCRIPTION = "description"
ATTR_ID = "id"
ATTR_PUBLICATION_DATE = "publication_date"
ATTR_SOURCE_TITLE = "sourceTitle"
ATTR_SOURCE_ORG = "sourceOrg"
ATTR_ESTA_ID = "estaid"
ATTR_RESOURCES = "resources"
ATTRIBUTION = "VICEmergency"
ATTR_SIZE = "size"
ATTR_SIZE_FMT = "sizefmt"
ATTR_LOCATION = "location"
ATTR_TEXT = "text"
ATTR_STATUS = "status"
ATTR_TYPE = "type"
ATTR_STATEWIDE = "statewide"

CONF_INC_CATEGORIES = "include_categories"
CONF_EXC_CATEGORIES = "exclude_categories"
CONF_STATEWIDE = "statewide"

DEFAULT_RADIUS_IN_KM = 20.0
DEFAULT_STATEWIDE = False

SCAN_INTERVAL = timedelta(minutes=5)

SIGNAL_DELETE_ENTITY = "vicemergency_feed_delete_{}"
SIGNAL_UPDATE_ENTITY = "vicemergency_feed_update_{}"

SOURCE = "vicemergency_feed"

VALID_CATEGORIES = ["Advice", "Emergency Warning", "Not Applicable", "Watch and Act", "Burn Area"]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_INC_CATEGORIES, default=[]): vol.All(
            cv.ensure_list, [vol.In(VALID_CATEGORIES)]
        ),
        vol.Optional(CONF_EXC_CATEGORIES, default=[]): vol.All(
            cv.ensure_list, [vol.In(VALID_CATEGORIES)]
        ),
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
        vol.Optional(CONF_RADIUS, default=DEFAULT_RADIUS_IN_KM): vol.Coerce(float),
        vol.Optional(CONF_STATEWIDE, default=DEFAULT_STATEWIDE): vol.Coerce(bool),
    }
)


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
):
    """Set up the VICEmergency Feed platform."""
    scan_interval = config.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL)
    coordinates = (
        config.get(CONF_LATITUDE, hass.config.latitude),
        config.get(CONF_LONGITUDE, hass.config.longitude),
    )
    radius_in_km = config[CONF_RADIUS]
    inc_categories = config.get(CONF_INC_CATEGORIES)
    exc_categories = config.get(CONF_EXC_CATEGORIES)
    # Initialize the entity manager.
    manager = VICEmergencyFeedEntityManager(
        hass, async_add_entities, scan_interval, coordinates, radius_in_km, inc_categories, exc_categories
    )

    async def start_feed_manager(event):
        """Start feed manager."""
        await manager.async_init()

    async def stop_feed_manager(event):
        """Stop feed manager."""
        await manager.async_stop()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, start_feed_manager)
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop_feed_manager)
    hass.async_create_task(manager.async_update())


class VICEmergencyFeedEntityManager:
    """Feed Entity Manager for VICEmergency Service GeoJSON feed."""

    def __init__(
        self,
        hass,
        async_add_entities,
        scan_interval,
        coordinates,
        radius_in_km,
        inc_categories,
        exc_categories,
    ):
        """Initialize the Feed Entity Manager."""
        self._hass = hass
        websession = aiohttp_client.async_get_clientsession(hass)
        self._feed_manager = VICEmergencyIncidentsFeedManager(
            websession,
            self._generate_entity,
            self._update_entity,
            self._remove_entity,
            coordinates,
            filter_radius=radius_in_km,
            filter_inc_categories=inc_categories,
            filter_exc_categories=exc_categories,
        )
        self._async_add_entities = async_add_entities
        self._scan_interval = scan_interval
        self._track_time_remove_callback = None

    async def async_init(self):
        """Schedule initial and regular updates based on configured time interval."""

        async def update(event_time):
            """Update."""
            await self.async_update()

        # Trigger updates at regular intervals.
        self._track_time_remove_callback = async_track_time_interval(
            self._hass, update, self._scan_interval
        )

        _LOGGER.debug("Feed entity manager initialized")

    async def async_update(self):
        """Refresh data."""
        await self._feed_manager.update()
        _LOGGER.debug("Feed entity manager updated")

    async def async_stop(self):
        """Stop this feed entity manager from refreshing."""
        if self._track_time_remove_callback:
            self._track_time_remove_callback()
        _LOGGER.debug("Feed entity manager stopped")

    def get_entry(self, external_id):
        """Get feed entry by external id."""
        return self._feed_manager.feed_entries.get(external_id)

    async def _generate_entity(self, external_id):
        """Generate new entity."""
        new_entity = VICEmergencyLocationEvent(self, external_id)
        # Add new entities to HA.
        self._async_add_entities([new_entity], True)

    async def _update_entity(self, external_id):
        """Update entity."""
        async_dispatcher_send(self._hass, SIGNAL_UPDATE_ENTITY.format(external_id))

    async def _remove_entity(self, external_id):
        """Remove entity."""
        async_dispatcher_send(self._hass, SIGNAL_DELETE_ENTITY.format(external_id))


class VICEmergencyLocationEvent(GeolocationEvent):
    """This represents an external event with VICEmergency data."""

    def __init__(self, feed_manager, external_id):
        """Initialize entity with data from feed entry."""
        self._feed_manager = feed_manager
        self._external_id = external_id
        self._name = None
        self._distance = None
        self._latitude = None
        self._longitude = None
        self._attribution = None
        self._remove_signal_delete = None
        self._remove_signal_update = None
        self._category1 = None
        self._category2 = None
        self._description = None
        self._id = None
        self._sourceTitle = None
        self._sourceOrg = None
        self._resources = None
        self._size = None
        self._sizefmt = None
        self._location = None
        self._status = None
        self._type = None
        self._statewide = None
        self._description = None

    async def async_added_to_hass(self):
        """Call when entity is added to hass."""
        self._remove_signal_delete = async_dispatcher_connect(
            self.hass,
            SIGNAL_DELETE_ENTITY.format(self._external_id),
            self._delete_callback,
        )
        self._remove_signal_update = async_dispatcher_connect(
            self.hass,
            SIGNAL_UPDATE_ENTITY.format(self._external_id),
            self._update_callback,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Call when entity will be removed from hass."""
        self._remove_signal_delete()
        self._remove_signal_update()

    @callback
    def _delete_callback(self):
        """Remove this entity."""
        self.hass.async_create_task(self.async_remove())

    @callback
    def _update_callback(self):
        """Call update method."""
        self.async_schedule_update_ha_state(True)

    @property
    def should_poll(self):
        """No polling needed for VICEmergency location events."""
        return False

    async def async_update(self):
        """Update this entity from the data held in the feed manager."""
        _LOGGER.debug("Updating %s", self._external_id)
        feed_entry = self._feed_manager.get_entry(self._external_id)
        if feed_entry:
            self._update_from_feed(feed_entry)

    def _update_from_feed(self, feed_entry):
        """Update the internal state from the provided feed entry."""
        self._name = feed_entry.category1 + " - " + feed_entry.location
        self._distance = feed_entry.distance_to_home
        self._latitude = feed_entry.coordinates[0]
        self._longitude = feed_entry.coordinates[1]
        self._attribution = feed_entry.attribution
        self._publication_date = feed_entry.publication_date
        self._location = feed_entry.location
        self._category1 = feed_entry.category1
        self._category2 = feed_entry.category2
        self._description = feed_entry.description
        self._external_id = feed_entry.etsa_id
        self._sourceOrg = feed_entry.source_organisation
        self._resources = feed_entry.resources
        self._size = feed_entry.size
        self._sizefmt = feed_entry.size_fmt
        self._location = feed_entry.location
        self._status = feed_entry.status
        self._type = feed_entry.type
        self._statewide = feed_entry.statewide
        self._description = feed_entry.description

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        if self._status == "Safe" or self._status == "Complete":
            return "mdi:map-marker-check"
        if self._status == "Unknown":
            return "mdi:map-marker-question"
        if self._category1 == "Rescue" and self._category2 == "Rescue Road Trap":
            return "mdi:car-emergency"
        if self._category1 == "Fire":
            if self._status == "Under Control":
                return "mdi:fire"
            return "mdi:fire-alert"
        if self._category1 == "Tree Down":
            return "mdi:tree"
        if self._category1 == "Flooding":
            return "mdi:house-flood"
        if self._status == "Warning":
            return "mdi:alert"
        return "mdi:alarm-light"

    @property
    def source(self) -> str:
        """Return source value of this external event."""
        return SOURCE

    @property
    def name(self) -> Optional[str]:
        """Return the name of the entity."""
        return self._name

    @property
    def distance(self) -> Optional[float]:
        """Return distance value of this external event."""
        return self._distance

    @property
    def latitude(self) -> Optional[float]:
        """Return latitude value of this external event."""
        return self._latitude

    @property
    def longitude(self) -> Optional[float]:
        """Return longitude value of this external event."""
        return self._longitude

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return LENGTH_KILOMETERS

    @property
    def device_state_attributes(self):
        """Return the device state attributes."""
        attributes = {}
        for key, value in (
            (ATTR_ID, self._id),
            (ATTR_LOCATION, self._location),
            (ATTR_ATTRIBUTION, self._attribution),
            (ATTR_CATEGORY1, self._category1),
            (ATTR_CATEGORY2, self._category2),
            (ATTR_DESCRIPTION, self._description),
            (ATTR_PUBLICATION_DATE, self._publication_date),
            (ATTR_SOURCE_TITLE, self._sourceTitle),
            (ATTR_SOURCE_ORG, self._sourceOrg),
            (ATTR_RESOURCES, self._resources),
            (ATTR_SIZE, self._size),
            (ATTR_SIZE_FMT, self._sizefmt),
            (ATTR_LOCATION, self._location),
            (ATTR_STATUS, self._status),
            (ATTR_STATEWIDE,self._statewide),
            (ATTR_TYPE, self._type), 
            (ATTR_DESCRIPTION, self._description),
        ):
            if value or isinstance(value, bool):
                attributes[key] = value
        return attributes
