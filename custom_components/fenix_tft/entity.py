"""Base entity for Fenix TFT integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FenixTFTCoordinator

if TYPE_CHECKING:
    from pyfenixcontrol import Device


def _get_device_name(dev: Device | None) -> str:
    """Build device name from installation and room names."""
    if not dev:
        return "Fenix TFT"

    installation = dev.installation_name or "Fenix TFT"
    room = dev.name or "Unnamed Device"

    if installation and room:
        return f"{installation} {room}"
    return installation or room or "Fenix TFT"


class FenixTFTEntity(CoordinatorEntity[FenixTFTCoordinator]):
    """Base class for Fenix TFT entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FenixTFTCoordinator, device_id: str) -> None:
        """Initialize a Fenix TFT entity."""
        super().__init__(coordinator)
        self._device_id = device_id

        # Find device data from coordinator
        dev = self._device
        device_name = _get_device_name(dev)

        # Register device info - shared across all entities for the same device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Fenix",
            model="TFT WiFi Thermostat",
            sw_version=dev.software_version if dev else None,
            hw_version=dev.model if dev else None,
            serial_number=dev.id if dev else None,
        )

    @property
    def _device(self) -> Device | None:
        """Return the device state for this entity from coordinator data."""
        return self.coordinator.data.devices.get(self._device_id)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Requires coordinator connection and device data
        dev = self._device
        return super().available and dev is not None
