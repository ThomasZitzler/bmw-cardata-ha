"""Device tracker for BMW CarData vehicles."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import TrackerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN
from .coordinator import CardataCoordinator
from .entity import CardataEntity

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

LATITUDE_DESCRIPTOR = "vehicle.cabin.infotainment.navigation.currentLocation.latitude"
LONGITUDE_DESCRIPTOR = "vehicle.cabin.infotainment.navigation.currentLocation.longitude"
HEADING_DESCRIPTOR = "vehicle.cabin.infotainment.navigation.currentLocation.heading"
GPS_FIX_STATUS_DESCRIPTOR = "vehicle.cabin.infotainment.navigation.currentLocation.fixStatus"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BMW CarData device tracker from config entry."""
    coordinator: CardataCoordinator = hass.data[DOMAIN][config_entry.entry_id].coordinator

    entities: list[BMWCarDataDeviceTracker] = []
    
    _LOGGER.debug("Setting up BMW CarData device tracker")

    # Create device tracker for each vehicle that has location data
    vins_processed = []
    for vin, _ in coordinator.iter_descriptors(binary=False):
        if vin not in vins_processed:
            vins_processed.append(vin)
            # Check if this VIN has latitude/longitude data
            lat_state = coordinator.get_state(vin, LATITUDE_DESCRIPTOR)
            lon_state = coordinator.get_state(vin, LONGITUDE_DESCRIPTOR)
            
            _LOGGER.debug(
                "VIN %s: lat_state=%s, lon_state=%s", 
                vin, 
                lat_state.value if lat_state else None,
                lon_state.value if lon_state else None
            )
            
            if lat_state is not None or lon_state is not None:
                _LOGGER.debug("Creating device tracker for VIN %s", vin)
                entities.append(BMWCarDataDeviceTracker(coordinator, vin))
            else:
                _LOGGER.debug("No location data available for VIN %s", vin)

    _LOGGER.debug("Created %d device tracker entities", len(entities))
    if entities:
        async_add_entities(entities)
    else:
        _LOGGER.warning("No device tracker entities created - no vehicles with location data found")


class BMWCarDataDeviceTracker(CardataEntity, TrackerEntity):
    """BMW CarData device tracker."""

    _attr_should_poll = False
    _attr_force_update = False
    _attr_translation_key = "vehicle_location"
    _attr_name = "Vehicle Location"

    def __init__(
        self,
        coordinator: CardataCoordinator,
        vin: str,
    ) -> None:
        """Initialize the Device Tracker."""
        # Use the latitude descriptor as the base descriptor for proper device association
        super().__init__(coordinator, vin, LATITUDE_DESCRIPTOR)
        self._attr_unique_id = f"{vin}_location"
        self._unsubscribe = None

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device."""
        return SourceType.GPS

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        
        # Subscribe to coordinator updates
        self._unsubscribe = async_dispatcher_connect(
            self.hass,
            self._coordinator.signal_update,
            self._handle_update,
        )
        
        # Initial update for all location descriptors
        self._handle_update(self._vin, LATITUDE_DESCRIPTOR)
        self._handle_update(self._vin, LONGITUDE_DESCRIPTOR)
        
        _LOGGER.debug("Device tracker added for VIN %s", self._vin)

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity which will be removed."""
        if self._unsubscribe is not None:
            self._unsubscribe()

    def _handle_update(self, vin: str, descriptor: str) -> None:
        """Handle updated data from the coordinator."""
        # Only update if this is for our vehicle and a location-related descriptor
        if vin != self._vin:
            return
            
        if descriptor not in [LATITUDE_DESCRIPTOR, LONGITUDE_DESCRIPTOR, HEADING_DESCRIPTOR, GPS_FIX_STATUS_DESCRIPTOR]:
            return
            
        # Schedule an update when any location data changes
        _LOGGER.debug("Device tracker update triggered for VIN %s, descriptor %s", vin, descriptor)
        self.schedule_update_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = super().extra_state_attributes
        
        # Add heading if available
        heading_state = self._coordinator.get_state(self._vin, HEADING_DESCRIPTOR)
        if heading_state is not None and heading_state.value is not None:
            attrs["direction"] = heading_state.value
        
        # Add GPS fix status if available
        gps_fix_state = self._coordinator.get_state(self._vin, GPS_FIX_STATUS_DESCRIPTOR)
        if gps_fix_state is not None and gps_fix_state.value is not None:
            attrs["gps_accuracy"] = gps_fix_state.value
            
        return attrs

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        lat_state = self._coordinator.get_state(self._vin, LATITUDE_DESCRIPTOR)
        if lat_state is not None and lat_state.value is not None:
            try:
                return float(lat_state.value)
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Invalid latitude value for %s: %s", self._vin, lat_state.value
                )
        return None

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        lon_state = self._coordinator.get_state(self._vin, LONGITUDE_DESCRIPTOR)
        if lon_state is not None and lon_state.value is not None:
            try:
                return float(lon_state.value)
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Invalid longitude value for %s: %s", self._vin, lon_state.value
                )
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Device tracker is available if we have at least one coordinate
        lat = self.latitude
        lon = self.longitude
        available = lat is not None or lon is not None
        
        # Also check GPS fix status for better availability determination
        gps_fix_state = self._coordinator.get_state(self._vin, GPS_FIX_STATUS_DESCRIPTOR)
        if gps_fix_state is not None and gps_fix_state.value == "NO_FIX":
            available = False
        
        if not available:
            _LOGGER.debug(
                "Device tracker for VIN %s not available - lat: %s, lon: %s, gps_fix: %s", 
                self._vin, lat, lon, 
                gps_fix_state.value if gps_fix_state else "unknown"
            )
        
        return available