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

This 
