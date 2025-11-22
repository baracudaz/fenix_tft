"""Platform for Fenix TFT climate entities."""

import logging
from datetime import datetime
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
from homeassistant.util import dt as dt_util

from . import FenixTFTConfigEntry
from .api import FenixTFTApiError
from .const import HOLIDAY_EPOCH_DATE, HOLIDAY_MODE_NONE
from .entity import FenixTFTEntity

_LOGGER = logging.getLogger(__name__)

# Reusable error message when device controls are locked by an active holiday schedule
HOLIDAY_LOCKED_MSG = "Holiday schedule active"

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
        holiday_mode = dev.get("holiday_mode", HOLIDAY_MODE_NONE)
        holiday_start = dev.get("holiday_start")
        holiday_end = dev.get("holiday_end")

        if (
            holiday_mode == HOLIDAY_MODE_NONE
            or not holiday_start
            or not holiday_end
            or HOLIDAY_EPOCH_DATE in (holiday_start, holiday_end)
        ):
            return False

        try:
            tz = dt_util.get_default_time_zone()
            start_dt = datetime.strptime(holiday_start, "%d/%m/%Y %H:%M:%S").replace(
                tzinfo=tz
            )
            end_dt = datetime.strptime(holiday_end, "%d/%m/%Y %H:%M:%S").replace(
                tzinfo=tz
            )
        except (ValueError, TypeError):
            return True  # Fallback: treat as active
        else:
            now = dt_util.now()
            return start_dt <= now <= end_dt

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
        if not dev:
            return ClimateEntityFeature(0)
        # Disable all controls if holiday is active
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
        if self._attr_device_info:
            if isinstance(self._attr_device_info, dict):
                dev_name = self._attr_device_info.get("name")
            else:
                dev_name = getattr(self._attr_device_info, "name", None)
        else:
            dev_name = None
        _LOGGER.debug(
            "Device %s (%s) preset mode: %s (%s)",
            self._device_id,
            dev_name,
            raw_preset,
            hvac_mode_str,
        )

        # Map device modes to Home Assistant HVAC modes
        if hvac_mode_str == "off":
            return HVACMode.OFF
        if hvac_mode_str == "manual":
            return HVACMode.HEAT  # Manual temperature control
        # Treat holiday mode as AUTO but lock controls elsewhere
        return HVACMode.AUTO  # Automatic/program / holiday / other modes

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return selectable HVAC modes (restricted during holiday)."""
        if self._is_holiday_active():
            return [self.hvac_mode]
        return self._attr_hvac_modes

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature on the device."""
        if self._is_holiday_active():
            _LOGGER.debug(
                "Ignoring temperature change for %s - holiday active",
                self._device_id,
            )
            msg = HOLIDAY_LOCKED_MSG
            raise HomeAssistantError(msg)
        temp: float | None = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return

        try:
            # Send temperature change to device via API
            await self._api.set_device_temperature(self._device_id, temp)
            # Request fresh data from coordinator to update UI
            await self.coordinator.async_request_refresh()
        except (aiohttp.ClientError, FenixTFTApiError):
            _LOGGER.exception(
                "Failed to set temperature for device %s", self._device_id
            )
            raise

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode by mapping to appropriate device preset mode."""
        if self._is_holiday_active():
            _LOGGER.debug(
                "Ignoring HVAC mode change for %s - holiday active",
                self._device_id,
            )
            msg = HOLIDAY_LOCKED_MSG
            raise HomeAssistantError(msg)
        _LOGGER.debug(
            "Setting HVAC mode to %s for device %s", hvac_mode, self._device_id
        )

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
            await self._api.set_device_preset_mode(self._device_id, preset_value)
        except (aiohttp.ClientError, FenixTFTApiError):
            _LOGGER.exception("Failed to set HVAC mode for device %s", self._device_id)
            raise

        # Update coordinator with optimistic data for immediate UI feedback
        self.coordinator.update_device_preset_mode(self._device_id, preset_value)
        # Force entity state update in Home Assistant
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode for special operations."""
        if self._is_holiday_active():
            _LOGGER.debug(
                "Ignoring preset mode change for %s - holiday active",
                self._device_id,
            )
            msg = HOLIDAY_LOCKED_MSG
            raise HomeAssistantError(msg)
        if preset_mode not in self._attr_preset_modes:
            _LOGGER.warning("Unsupported preset mode: %s", preset_mode)
            return

        # Convert preset mode string to device value
        preset_value = PRESET_INVERTED[preset_mode]
        _LOGGER.debug(
            "Setting preset mode to %s (%s) for device %s",
            preset_mode,
            preset_value,
            self._device_id,
        )

        try:
            # Send preset mode change to device
            await self._api.set_device_preset_mode(self._device_id, preset_value)
        except (aiohttp.ClientError, FenixTFTApiError):
            _LOGGER.exception(
                "Failed to set preset mode %s (%s) for device %s",
                preset_mode,
                preset_value,
                self._device_id,
            )
            raise

        # Update coordinator with optimistic data and force state update
        self.coordinator.update_device_preset_mode(self._device_id, preset_value)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Request latest data from coordinator (called by Home Assistant)."""
        await self.coordinator.async_request_refresh()
