# vicemergency_feed

This brings in daa from the VIC Emergency website into Home Assistant as geojson events.

This brings in all events from the VIC Emergency website from a large range of Victorian Government agencies, not all of whom fill in the same data into the feed.

## Setup

```yaml
geo_location:
  - platform: vicemergency_feed
    radius: 100
    exclude_categories: ['Burn Area']
    statewide: true
```

## Categories

Each incident has a main category (category1), and a sub-category (category2). Some examples of this are:

* include_categories - This is useful if you would only like certain categories, for instance you are only interested in fires.

## Statewide filter

At the moment, there is a permanent advice message that covers the entire state and covers the advice for COVID-19. Due to this not changing often, there is an option to remove these statewide advice messages. By setting this to true, you are including the statewide incidents. Setting this to false, will exclude them.

## TODO

* feedType

## Source Organisations

* SES - State Emergency Service
* FRV - Fire Rescue Victoria (the old Metropolitan Fire Bridge)
* CFA - Country Fire Authority (fires on private properties)
* DELWP - Department of Environment, Land, Water and Planning (fires and burn offs in state government land)
* EMV - Emergency Management Victoria (generally responsible for warning, advice and other information for incidents). Note this may also be related to other incidents.
