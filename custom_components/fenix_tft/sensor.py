"""Platform for Fenix TFT sensor entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FenixTFTCoordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import FenixTFTConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    _: HomeAssistant,
    entry: FenixTFTConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fenix TFT sensor entities from a config entry."""
    data = entry.runtime_data
    coordinator = data["coordinator"]

    if entities := [
        FenixFloorTempSensor(coordinator, dev["id"])
        for dev in coordinator.data
        if dev.get("floor_temp") is not None
    ]:
        async_add_entities(entities)


class FenixFloorTempSensor(CoordinatorEntity[FenixTFTCoordinator], SensorEntity):
    """Representation of a Fenix TFT floor temperature sensor."""

    _attr_has_entity_name = True
    _attr_translation_key = "floor_temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT floor temperature sensor."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_floor_temperature"

        # Find device data from coordinator
        dev = self._device

        # Build device name from installation and room names
        installation = dev.get("installation") if dev else ""
        room = dev.get("name") if dev else ""

        if installation and room:
            device_name = f"{installation} {room}"
        elif installation:
            device_name = installation
        elif room:
            device_name = room
        else:
            device_name = "Fenix TFT"

        # Register device info - this should match the climate entity's device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Fenix",
            model="TFT WiFi Thermostat",
            sw_version=dev.get("software") if dev else None,
            hw_version=dev.get("type") if dev else None,
            serial_number=dev.get("id") if dev else None,
        )

    @property
    def _device(self) -> dict[str, Any] | None:
        """Return the device dict for this entity from coordinator data."""
        return next(
            (d for d in self.coordinator.data if d["id"] == self._device_id),
            None,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Requires coordinator connection and device data with floor_temp
        dev = self._device
        return (
            super().available and dev is not None and dev.get("floor_temp") is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return the current floor temperature."""
        dev = self._device
        return dev.get("floor_temp") if dev else None

    async def async_update(self) -> None:
        """Request latest data from coordinator (called by Home Assistant)."""
        await self.coordinator.async_request_refresh()
