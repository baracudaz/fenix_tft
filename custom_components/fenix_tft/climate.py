"""Platform for Fenix TFT climate entities."""

import logging
from typing import Any, ClassVar

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Map Fenix TFT API hvac_action values to Home Assistant HVAC actions
FENIX_TFT_TO_HASS_HVAC_ACTION: dict[int | None, HVACAction] = {
    1: HVACAction.HEATING,  # Device is actively heating
    2: HVACAction.OFF,  # Device is off
    0: HVACAction.IDLE,  # Device is on but not heating
    None: HVACAction.OFF,  # Fallback for unknown states
}

# Map Fenix TFT preset mode values to operational mode strings
HVAC_MODE_MAP: dict[int, str] = {
    0: "off",  # Device is turned off
    1: "holidays",  # Holiday mode (reduced heating)
    2: "auto",  # Automatic program mode
    6: "manual",  # Manual temperature control
}
HVAC_MODE_INVERTED: dict[str, int] = {v: k for k, v in HVAC_MODE_MAP.items()}

# Map special preset modes that don't fit into basic HVAC modes
PRESET_MAP: dict[int, str] = {
    2: "program",  # Follow programmed schedule
    4: "defrost",  # Defrost cycle
    5: "boost",  # Boost heating mode
}
PRESET_INVERTED: dict[str, int] = {v: k for k, v in PRESET_MAP.items()}


async def async_setup_entry(
    _: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: Any,
) -> None:
    """Set up Fenix TFT climate entities from a config entry."""
    # Get runtime data stored by the integration setup
    data = entry.runtime_data
    coordinator = data["coordinator"]
    api = data["api"]

    # Create climate entities for each device found by the coordinator
    entities = [
        FenixTFTClimate(api, dev["id"], coordinator) for dev in coordinator.data
    ]
    async_add_entities(entities)


class FenixTFTClimate(CoordinatorEntity, ClimateEntity):
    """Representation of a Fenix TFT climate entity."""

    # Define supported HVAC modes for this thermostat
    _attr_hvac_modes: ClassVar[list[HVACMode]] = [
        HVACMode.HEAT,  # Manual heating mode
        HVACMode.AUTO,  # Automatic/program mode
        HVACMode.OFF,  # Device off
    ]

    # Define supported preset modes for special operations
    _attr_preset_modes: ClassVar[list[str]] = [
        "program",  # Follow programmed schedule
        "defrost",  # Defrost cycle
        "boost",  # Boost heating
    ]

    _attr_temperature_unit: ClassVar[str] = UnitOfTemperature.CELSIUS
    _attr_has_entity_name: bool = True  # Use modern entity naming
    _attr_translation_key: str = "thermostat"  # Translation key for entity name

    def __init__(self, api: Any, device_id: str, coordinator: Any) -> None:
        """Initialize a Fenix TFT climate entity."""
        super().__init__(coordinator)
        self._api = api
        self._id = device_id
        self._attr_unique_id = device_id

        # Find device data from coordinator
        dev = next((d for d in coordinator.data if d["id"] == device_id), None)

        # Build device name from installation and room names
        # This creates names like "Victory Port Kúpelňa" for better identification
        installation = (
            dev.get("installation") if dev and dev.get("installation") else ""
        )
        room = dev.get("name") if dev and dev.get("name") else ""

        if installation and room:
            device_name = f"{installation} {room}"  # "Victory Port Kúpelňa"
        elif installation:
            device_name = installation  # Just installation name
        elif room:
            device_name = room  # Just room name
        else:
            device_name = "Fenix TFT"  # Fallback name

        # Register device info for Home Assistant device registry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},  # Unique device identifier
            name=device_name,  # Display name in device registry
            manufacturer="Fenix",
            model="TFT WiFi Thermostat",
            sw_version=dev.get("version") if dev else None,
            hw_version=dev.get("model") if dev else None,
            serial_number=dev.get("id") if dev else None,
        )

        # Set entity name to None - this tells Home Assistant to use the device
        # name for both the entity display name and entity ID generation
        # Result: Entity name = "Victory Port Kúpelňa",
        # Entity ID = "climate.victory_port_kupelna"
        self._attr_name = None

    @property
    def _device(self) -> dict[str, Any] | None:
        """Return the device dict for this entity from coordinator data."""
        return next((d for d in self.coordinator.data if d["id"] == self._id), None)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Requires coordinator connection and device data
        return super().available and self._device is not None

    def _get_preset_mode(self) -> str | None:
        """Get the current preset mode string from device data."""
        dev = self._device
        if not dev:
            return None
        raw_preset = dev.get("preset_mode")
        if raw_preset is None:
            return None
        # Convert numeric preset mode to string using mapping
        return PRESET_MAP.get(raw_preset)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature measured by the thermostat."""
        dev = self._device
        return dev.get("current_temp") if dev else None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature set on the thermostat."""
        dev = self._device
        return dev.get("target_temp") if dev else None

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current HVAC action (heating, idle, off)."""
        dev = self._device
        raw_action = dev.get("hvac_action") if dev else None
        # Map device's numeric action to Home Assistant's HVAC action
        return FENIX_TFT_TO_HASS_HVAC_ACTION.get(raw_action, HVACAction.OFF)

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode if it's in our supported list."""
        preset = self._get_preset_mode()
        # Only return preset if it's in our supported modes list
        return preset if preset in self._attr_preset_modes else None

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return supported features based on current device mode."""
        dev = self._device
        raw_preset = dev.get("preset_mode") if dev else None
        hvac_mode_str = (
            HVAC_MODE_MAP.get(raw_preset) if raw_preset is not None else None
        )

        # Enable temperature control only in manual mode
        if hvac_mode_str == "manual":
            return (
                ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.PRESET_MODE
            )
        # In other modes, only preset mode changes are supported
        return ClimateEntityFeature.PRESET_MODE

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode based on device preset mode."""
        dev = self._device
        raw_preset = dev.get("preset_mode") if dev else None
        hvac_mode_str = (
            HVAC_MODE_MAP.get(raw_preset) if raw_preset is not None else None
        )
        _LOGGER.debug(
            "Device %s preset mode: %s (%s)", self._id, raw_preset, hvac_mode_str
        )

        # Map device modes to Home Assistant HVAC modes
        if hvac_mode_str == "off":
            return HVACMode.OFF
        if hvac_mode_str == "manual":
            return HVACMode.HEAT  # Manual temperature control
        return HVACMode.AUTO  # Automatic/program modes

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature on the device."""
        temp: float | None = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return

        # Send temperature change to device via API
        await self._api.set_device_temperature(self._id, temp)
        # Request fresh data from coordinator to update UI
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode by mapping to appropriate device preset mode."""
        _LOGGER.debug("Setting HVAC mode to %s for device %s", hvac_mode, self._id)

        # Map Home Assistant HVAC mode to device preset mode value
        if hvac_mode == HVACMode.OFF:
            preset_value = HVAC_MODE_INVERTED["off"]  # 0
        elif hvac_mode == HVACMode.AUTO:
            preset_value = HVAC_MODE_INVERTED["auto"]  # 2
        elif hvac_mode == HVACMode.HEAT:
            preset_value = HVAC_MODE_INVERTED["manual"]  # 6
        else:
            _LOGGER.warning("Unsupported HVAC mode: %s", hvac_mode)
            return

        try:
            # Send mode change to device
            await self._api.set_device_preset_mode(self._id, preset_value)
        except Exception:
            _LOGGER.exception("Failed to set HVAC mode for device %s", self._id)
            raise

        # Update coordinator with optimistic data for immediate UI feedback
        self.coordinator.update_device_preset_mode(self._id, preset_value)
        # Force entity state update in Home Assistant
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode for special operations."""
        if preset_mode not in self._attr_preset_modes:
            _LOGGER.warning("Unsupported preset mode: %s", preset_mode)
            return

        # Convert preset mode string to device value
        preset_value = PRESET_INVERTED[preset_mode]
        _LOGGER.debug(
            "Setting preset mode to %s (%s) for device %s",
            preset_mode,
            preset_value,
            self._id,
        )

        try:
            # Send preset mode change to device
            await self._api.set_device_preset_mode(self._id, preset_value)
        except Exception:
            _LOGGER.exception(
                "Failed to set preset mode %s (%s) for device %s",
                preset_mode,
                preset_value,
                self._id,
            )
            raise

        # Update coordinator with optimistic data and force state update
        self.coordinator.update_device_preset_mode(self._id, preset_value)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Request latest data from coordinator (called by Home Assistant)."""
        await self.coordinator.async_request_refresh()
