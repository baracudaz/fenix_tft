"""Platform for Fenix TFT climate entities."""

import logging
from typing import Any, ClassVar

import aiohttp
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import FenixTFTConfigEntry
from .api import FenixTFTApiError
from .const import (
    HOLIDAY_LOCKED_MSG,
    PRESET_MODE_BOOST,
    PRESET_MODE_DEFROST,
    PRESET_MODE_HOLIDAYS,
    PRESET_MODE_MANUAL,
    PRESET_MODE_OFF,
    PRESET_MODE_PROGRAM,
)
from .entity import FenixTFTEntity

_LOGGER = logging.getLogger(__name__)


# Configure parallel updates for climate platform - serialize to prevent API overwhelm
PARALLEL_UPDATES = 1

# Map Fenix TFT API hvac_action values to Home Assistant HVAC actions
FENIX_TFT_TO_HASS_HVAC_ACTION: dict[int | None, HVACAction] = {
    1: HVACAction.HEATING,  # Device is actively heating
    2: HVACAction.OFF,  # Device is off
    0: HVACAction.IDLE,  # Device is on but not heating
    None: HVACAction.OFF,  # Fallback for unknown states
}

# Map Fenix TFT preset mode values to operational mode strings
# Used to determine which Home Assistant HVAC mode to display
HVAC_MODE_MAP: dict[int, str] = {
    PRESET_MODE_OFF: "off",  # Device is turned off
    PRESET_MODE_HOLIDAYS: "holidays",  # Holiday mode (reduced heating)
    PRESET_MODE_PROGRAM: "auto",  # Automatic program mode
    PRESET_MODE_MANUAL: "manual",  # Manual temperature control
}

# Map device preset_mode values to Home Assistant preset mode strings
# Note: PRESET_MODE_PROGRAM (2) appears in both maps - shows as AUTO + "program"
PRESET_MAP: dict[int, str] = {
    PRESET_MODE_PROGRAM: "program",  # Follow programmed schedule
    PRESET_MODE_DEFROST: "defrost",  # Defrost cycle
    PRESET_MODE_BOOST: "boost",  # Boost heating mode
}
PRESET_INVERTED: dict[str, int] = {v: k for k, v in PRESET_MAP.items()}


async def async_setup_entry(
    _: HomeAssistant,
    entry: FenixTFTConfigEntry,
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


class FenixTFTClimate(FenixTFTEntity, ClimateEntity):
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
    _attr_translation_key: str = "thermostat"  # Translation key for entity name

    def __init__(self, api: Any, device_id: str, coordinator: Any) -> None:
        """Initialize a Fenix TFT climate entity."""
        super().__init__(coordinator, device_id)
        self._api = api
        self._attr_unique_id = device_id

        # Set entity name to None - this tells Home Assistant to use the device
        # name for both the entity display name and entity ID generation
        # Result: Entity name = "Victory Port Kúpelňa",
        # Entity ID = "climate.victory_port_kupelna"
        self._attr_name = None

    def _get_preset_mode(self) -> str | None:
        """Get the current preset mode string from device data."""
        dev = self._device
        if not dev:
            return None
        raw_preset = dev.get("preset_mode")
        return None if raw_preset is None else PRESET_MAP.get(raw_preset)

    def _is_holiday_active(self) -> bool:
        """Return True if device is currently in an active holiday schedule."""
        dev = self._device
        if not dev:
            return False
        # Holiday is active when preset_mode is HOLIDAYS
        return dev.get("preset_mode") == PRESET_MODE_HOLIDAYS

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature measured by the thermostat."""
        dev = self._device
        return dev.get("current_temp") if dev else None

    @property
    def target_temperature(self) -> float | None:
        """
        Return the target temperature set on the thermostat.

        Note: In holiday mode, returns the normal target (Ma) that will resume
        after holiday ends. The active holiday target (Sp) is shown as an attribute.
        """
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
        if not dev:
            return ClimateEntityFeature(0)

        # In holiday mode: disable all controls (locked)
        # Holiday target temp will be shown as an attribute instead
        if self._is_holiday_active():
            return ClimateEntityFeature(0)

        raw_preset = dev.get("preset_mode")
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
        # Map device modes to Home Assistant HVAC modes (holiday treated as AUTO)
        return (
            HVACMode.OFF
            if hvac_mode_str == "off"
            else HVACMode.HEAT
            if hvac_mode_str == "manual"
            else HVACMode.AUTO
        )

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return selectable HVAC modes (restricted during holiday)."""
        return [self.hvac_mode] if self._is_holiday_active() else self._attr_hvac_modes

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature on the device."""
        temp: float | None = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            _LOGGER.debug(
                "Temperature change ignored for device %s: no temperature provided",
                self._device_id,
            )
            return

        if self._is_holiday_active():
            _LOGGER.warning(
                "Temperature change blocked for device %s: holiday mode active",
                self._device_id,
            )
            msg = HOLIDAY_LOCKED_MSG
            raise HomeAssistantError(msg)

        _LOGGER.debug(
            "Setting temperature for device %s: %.1f°C",
            self._device_id,
            temp,
        )

        try:
            # Send temperature change to device via API
            await self._api.set_device_temperature(self._device_id, temp)
            _LOGGER.info(
                "Temperature set successfully for device %s: %.1f°C",
                self._device_id,
                temp,
            )
            # Request fresh data from coordinator to update UI
            await self.coordinator.async_request_refresh()
        except (aiohttp.ClientError, FenixTFTApiError):
            _LOGGER.exception(
                "Failed to set temperature for device %s to %.1f°C",
                self._device_id,
                temp,
            )
            raise

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode by mapping to appropriate device preset mode."""
        if self._is_holiday_active():
            _LOGGER.warning(
                "HVAC mode change blocked for device %s: holiday mode active",
                self._device_id,
            )
            msg = HOLIDAY_LOCKED_MSG
            raise HomeAssistantError(msg)

        # Map Home Assistant HVAC mode to device preset mode value
        if hvac_mode == HVACMode.OFF:
            preset_value = PRESET_MODE_OFF
        elif hvac_mode == HVACMode.AUTO:
            preset_value = PRESET_MODE_PROGRAM
        elif hvac_mode == HVACMode.HEAT:
            preset_value = PRESET_MODE_MANUAL
        else:
            _LOGGER.warning(
                "Unsupported HVAC mode for device %s: %s",
                self._device_id,
                hvac_mode,
            )
            return

        _LOGGER.debug(
            "Setting HVAC mode for device %s: %s (preset_mode=%s)",
            self._device_id,
            hvac_mode,
            preset_value,
        )

        try:
            # Send mode change to device
            await self._api.set_device_preset_mode(self._device_id, preset_value)
            _LOGGER.info(
                "HVAC mode set successfully for device %s: %s",
                self._device_id,
                hvac_mode,
            )
        except (aiohttp.ClientError, FenixTFTApiError):
            _LOGGER.exception(
                "Failed to set HVAC mode for device %s to %s",
                self._device_id,
                hvac_mode,
            )
            raise

        # Update coordinator with optimistic data for immediate UI feedback
        self.coordinator.update_device_preset_mode(self._device_id, preset_value)
        # Force entity state update in Home Assistant
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode for special operations."""
        if self._is_holiday_active():
            _LOGGER.warning(
                "Preset mode change blocked for device %s: holiday mode active",
                self._device_id,
            )
            msg = HOLIDAY_LOCKED_MSG
            raise HomeAssistantError(msg)

        if preset_mode not in self._attr_preset_modes:
            _LOGGER.warning(
                "Unsupported preset mode for device %s: %s (valid: %s)",
                self._device_id,
                preset_mode,
                self._attr_preset_modes,
            )
            return

        # Convert preset mode string to device value
        preset_value = PRESET_INVERTED[preset_mode]
        _LOGGER.debug(
            "Setting preset mode for device %s: %s (preset_mode=%s)",
            self._device_id,
            preset_mode,
            preset_value,
        )

        try:
            # Send preset mode change to device
            await self._api.set_device_preset_mode(self._device_id, preset_value)
            _LOGGER.info(
                "Preset mode set successfully for device %s: %s",
                self._device_id,
                preset_mode,
            )
        except (aiohttp.ClientError, FenixTFTApiError):
            _LOGGER.exception(
                "Failed to set preset mode for device %s to %s",
                self._device_id,
                preset_mode,
            )
            raise

        # Update coordinator with optimistic data and force state update
        self.coordinator.update_device_preset_mode(self._device_id, preset_value)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Request latest data from coordinator (called by Home Assistant)."""
        await self.coordinator.async_request_refresh()
