"""Device tracker for BMW CarData vehicles."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import TrackerEntity
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


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BMW CarData device tracker from config entry."""
    coordinator: CardataCoordinator = hass.data[DOMAIN][config_entry.entry_id].coordinator

    entities: list[BMWCarDataDeviceTracker] = []

    # Create device tracker for each vehicle that has location data
    for vin, _ in coordinator.iter_descriptors(binary=False):
        # Check if this VIN has latitude/longitude data
        lat_state = coordinator.get_state(vin, LATITUDE_DESCRIPTOR)
        lon_state = coordinator.get_state(vin, LONGITUDE_DESCRIPTOR)
        
        if lat_state is not None or lon_state is not None:
            entities.append(BMWCarDataDeviceTracker(coordinator, vin))

    if entities:
        async_add_entities(entities)


class BMWCarDataDeviceTracker(CardataEntity, TrackerEntity):
    """BMW CarData device tracker."""

    _attr_force_update = False
    _attr_translation_key = "vehicle_location"
    _attr_name = "Vehicle Location"

    def __init__(
        self,
        coordinator: CardataCoordinator,
        vin: str,
    ) -> None:
        """Initialize the Device Tracker."""
        super().__init__(coordinator, vin, "location")
        self._attr_unique_id = f"{vin}_location"
        self._unsubscribe = None

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        self._unsubscribe = async_dispatcher_connect(
            self.hass,
            self._coordinator.signal_update,
            self._handle_coordinator_update,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity which will be removed."""
        if self._unsubscribe is not None:
            self._unsubscribe()

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return entity specific state attributes."""
        attrs = super().extra_state_attributes
        
        # Add heading if available
        heading_state = self._coordinator.get_state(self._vin, HEADING_DESCRIPTOR)
        if heading_state is not None and heading_state.value is not None:
            attrs["direction"] = heading_state.value
            
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
        return self.latitude is not None or self.longitude is not None