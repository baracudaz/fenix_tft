"""Platform for Fenix TFT climate entities."""

import logging
import math
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_HVAC_MODE,
    PRESET_AWAY,
    PRESET_BOOST,
    PRESET_HOME,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pyfenixcontrol import FenixControlError

from .const import (
    DOMAIN,
    HOLIDAY_LOCKED_MSG,
    HOLIDAY_MODE_NONE,
    HVAC_ACTION_HEATING,
    PRESET_MODE_BOOST,
    PRESET_MODE_DEFROST,
    PRESET_MODE_HOLIDAYS,
    PRESET_MODE_MANUAL,
    PRESET_MODE_OFF,
    PRESET_MODE_PROGRAM,
    TEMP_MAX,
    TEMP_MIN,
    TEMP_STEP,
    TEMP_STEP_EPSILON,
)
from .entity import FenixTFTEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pyfenixcontrol import FenixControlClient

    from . import FenixTFTConfigEntry
    from .coordinator import FenixTFTCoordinator

_LOGGER = logging.getLogger(__name__)


# Configure parallel updates for climate platform - serialize to prevent API overwhelm
PARALLEL_UPDATES = 1

# Map Fenix TFT preset mode values to operational mode strings
# Used to determine which Home Assistant HVAC mode to display
HVAC_MODE_MAP: dict[int, str] = {
    PRESET_MODE_OFF: "off",  # Device is turned off
    PRESET_MODE_HOLIDAYS: "holidays",  # Holiday mode (reduced heating)
    PRESET_MODE_PROGRAM: "auto",  # Automatic program mode
    PRESET_MODE_MANUAL: "manual",  # Manual temperature control
}

# Modes that regulate to their own setpoint, reported as the active setpoint (Sp)
SETPOINT_PRESET_MODES: frozenset[int] = frozenset(
    {PRESET_MODE_PROGRAM, PRESET_MODE_DEFROST, PRESET_MODE_BOOST}
)
# Modes that regulate to a target temperature
TARGET_PRESET_MODES: frozenset[int] = SETPOINT_PRESET_MODES | {PRESET_MODE_MANUAL}
# Modes with their own setpoint (df, bo) besides manual (Ma): changing the target
# in them sets that setpoint and keeps the mode.
OWN_SETPOINT_PRESET_MODES: frozenset[int] = frozenset(
    {PRESET_MODE_DEFROST, PRESET_MODE_BOOST}
)

# Map device preset_mode values to Home Assistant's standard presets (same as the
# core fenix_control integration). Note: PRESET_MODE_PROGRAM (2) appears in both
# maps - shows as AUTO + "home".
PRESET_MAP: dict[int, str] = {
    PRESET_MODE_PROGRAM: PRESET_HOME,  # Follow programmed schedule
    PRESET_MODE_DEFROST: PRESET_AWAY,  # Defrost (frost protection setpoint)
    PRESET_MODE_BOOST: PRESET_BOOST,  # Boost (boost setpoint on the device)
}
PRESET_INVERTED: dict[str, int] = {
    PRESET_HOME: PRESET_MODE_PROGRAM,
    "program": PRESET_MODE_PROGRAM,
    PRESET_AWAY: PRESET_MODE_DEFROST,
    "defrost": PRESET_MODE_DEFROST,
    "eco": PRESET_MODE_DEFROST,  # Former preset name
    PRESET_BOOST: PRESET_MODE_BOOST,
    "comfort": PRESET_MODE_BOOST,  # Former preset name
}

# Older and FENIX names still accepted by climate.set_preset_mode
PRESET_CANONICAL_MAP: dict[str, str] = {
    PRESET_HOME: PRESET_HOME,
    "program": PRESET_HOME,
    PRESET_AWAY: PRESET_AWAY,
    "defrost": PRESET_AWAY,
    "eco": PRESET_AWAY,
    PRESET_BOOST: PRESET_BOOST,
    "comfort": PRESET_BOOST,
}

PRESET_ICON_MAP: dict[str, str] = {
    PRESET_HOME: "mdi:clock-outline",
    PRESET_AWAY: "mdi:snowflake",
    PRESET_BOOST: "mdi:fire",
}


async def async_setup_entry(
    _: HomeAssistant,
    entry: FenixTFTConfigEntry,
    async_add_entities: Any,
) -> None:
    """Set up Fenix TFT climate entities from a config entry."""
    # Get runtime data stored by the integration setup
    data = entry.runtime_data
    coordinator = data["coordinator"]
    client = data["client"]

    # Create climate entities for each device found by the coordinator
    entities = [
        FenixTFTClimate(client, device_id, coordinator)
        for device_id in coordinator.data.devices
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
        PRESET_HOME,  # Follow programmed schedule
        PRESET_AWAY,  # Defrost
        PRESET_BOOST,  # Boost
    ]
    _normalized_preset_modes: ClassVar[frozenset[str]] = frozenset(PRESET_INVERTED)

    _attr_native_temperature_unit: ClassVar[str] = UnitOfTemperature.CELSIUS
    _attr_translation_key: str = "thermostat"  # Translation key for entity name

    def __init__(
        self,
        client: FenixControlClient,
        device_id: str,
        coordinator: FenixTFTCoordinator,
    ) -> None:
        """Initialize a Fenix TFT climate entity."""
        super().__init__(coordinator, device_id)
        self._client = client
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
        raw_preset = dev.preset_mode
        return None if raw_preset is None else PRESET_MAP.get(raw_preset)

    def _is_holiday_active(self) -> bool:
        """
        Return True if device is currently in active holiday mode.

        Uses H4 (active_holiday_mode) as the primary indicator, which reflects
        the real-time holiday state regardless of the preset_mode setting.
        Only when H4 is HOLIDAY_MODE_NONE is the device truly available for control.
        """
        dev = self._device
        if not dev:
            return False
        # Holiday is active when H4 (active_holiday_mode) is not "none"
        # This is more reliable than checking preset_mode == HOLIDAYS
        active_holiday_mode = dev.active_holiday_mode
        return active_holiday_mode not in (None, HOLIDAY_MODE_NONE)

    @property
    def target_temperature_step(self) -> float:
        """
        Return the step the UI uses to change the target.

        Home Assistant doesn't convert the step: in Fahrenheit, 0.5 °F would be
        rounded back to the same 0.5 °C target, so whole degrees are used.
        """
        if self.hass.config.units.temperature_unit == UnitOfTemperature.CELSIUS:
            return TEMP_STEP
        return 1.0

    @property
    def native_current_temperature(self) -> float | None:
        """Return the current temperature measured by the thermostat."""
        dev = self._device
        return dev.room_temperature if dev else None

    @property
    def native_target_temperature(self) -> float | None:
        """
        Return the temperature the thermostat regulates to.

        Manual mode uses its own target (Ma), Defrost and Boost the setpoints set
        on the thermostat (df, bo), Program the setpoint the program currently
        uses (Sp). Off has no target. During a holiday no target is shown; the
        holiday setpoint is a sensor attribute.
        """
        dev = self._device
        if dev is None or dev.preset_mode not in TARGET_PRESET_MODES:
            return None
        if not self._is_holiday_active():
            if dev.preset_mode == PRESET_MODE_DEFROST:
                return dev.defrost_temperature
            if dev.preset_mode == PRESET_MODE_BOOST:
                return dev.boost_temperature
            if dev.preset_mode == PRESET_MODE_PROGRAM:
                return dev.active_target_temperature
        return dev.target_temperature

    def _setpoint_range(self, mode: int | None = None) -> tuple[float, float]:
        """
        Return the range the device accepts for the setpoint changed in a mode.

        Without a mode, the current mode of the device is used.

        Defrost and Boost have their own ranges (df, bo; for example 2-15 °C
        for frost protection on TFT thermostats); in the other modes a change
        sets the manual target (Ma, 10-30 °C on the WiFi Box). The bounds are
        rounded inwards to the 0.5 °C step; without a reported range the
        default 5-35 °C applies.
        """
        dev = self._device
        if dev is None:
            return TEMP_MIN, TEMP_MAX
        if mode is None:
            mode = dev.preset_mode
        if mode == PRESET_MODE_DEFROST:
            device_range = dev.defrost_temperature_range
        elif mode == PRESET_MODE_BOOST:
            device_range = dev.boost_temperature_range
        else:
            device_range = dev.target_temperature_range
        if device_range is None:
            return TEMP_MIN, TEMP_MAX
        # Round to 0.01 first: the °F conversion leaves tiny errors (10.000001).
        low = math.ceil(round(device_range[0], 2) / TEMP_STEP) * TEMP_STEP
        high = math.floor(round(device_range[1], 2) / TEMP_STEP) * TEMP_STEP
        if low > high:
            return TEMP_MIN, TEMP_MAX
        return low, high

    @property
    def min_temp(self) -> float:
        """Return the lowest target the device accepts in the current mode."""
        return self._setpoint_range()[0]

    @property
    def max_temp(self) -> float:
        """Return the highest target the device accepts in the current mode."""
        return self._setpoint_range()[1]

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current HVAC action (heating, idle, off)."""
        dev = self._device
        # During a holiday the heating state field carries the holiday mode
        if dev is None or dev.hvac_state is None or self._is_holiday_active():
            return None
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if dev.hvac_state == HVAC_ACTION_HEATING:
            return HVACAction.HEATING
        # Not heating. TFT thermostats report 2 for this (also when the target is
        # reached), the WiFi Box 0; only the off mode means the device is off.
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset mode if it's in our supported list."""
        preset = self._get_preset_mode()
        # Only return preset if it's in our supported modes list
        return preset if preset in self._attr_preset_modes else None

    @property
    def icon(self) -> str | None:
        """Return an icon that reflects the active preset mode in auto operation."""
        preset = self.preset_mode
        if preset is not None:
            icon = PRESET_ICON_MAP.get(preset.lower())
            if icon is not None:
                return icon
        return super().icon

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

        # Also while off: Home Assistant rejects a target sent together with an
        # HVAC mode if the feature is missing. No target is shown then.
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
        )

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode based on device preset mode."""
        dev = self._device
        raw_preset = dev.preset_mode if dev else None
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

        hvac_mode: HVACMode | None = kwargs.get(ATTR_HVAC_MODE)
        if hvac_mode is not None and hvac_mode not in self.hvac_modes:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_hvac_mode",
                translation_placeholders={"hvac_mode": hvac_mode},
            )
        dev = self._device
        current_mode = dev.preset_mode if dev is not None else None
        if hvac_mode is None and current_mode not in TARGET_PRESET_MODES:
            # A target alone must not turn on a thermostat that is off
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_target_mode"
            )
        # Defrost and Boost keep their mode and get a new setpoint; in the other
        # modes, or with an HVAC mode given, the change sets the manual target
        # and switches to manual.
        mode = (
            current_mode
            if hvac_mode is None and current_mode in OWN_SETPOINT_PRESET_MODES
            else PRESET_MODE_MANUAL
        )

        steps = temp / TEMP_STEP
        if self.hass.config.units.temperature_unit != UnitOfTemperature.CELSIUS:
            # Converted from Fahrenheit by Home Assistant (72 °F arrives as
            # 22.22 °C): use the nearest step instead of rejecting it
            temp = round(steps) * TEMP_STEP
        elif abs(steps - round(steps)) > TEMP_STEP_EPSILON:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="temperature_step_invalid",
                translation_placeholders={
                    "step": str(TEMP_STEP),
                    "temp": str(temp),
                },
            )

        low, high = self._setpoint_range(mode)
        if not low <= temp <= high:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="temperature_out_of_range",
                translation_placeholders={
                    "min": str(low),
                    "max": str(high),
                    "temp": str(temp),
                },
            )

        _LOGGER.debug(
            "Setting temperature for device %s: %.1f°C",
            self._device_id,
            temp,
        )

        try:
            await self._client.set_setpoint(self._device_id, mode, temp)
            _LOGGER.info(
                "Temperature set successfully for device %s: %.1f°C (mode %s)",
                self._device_id,
                temp,
                mode,
            )
            # Keep the mode and its new setpoint until the cloud reports them
            self.coordinator.update_device_preset_mode(
                self._device_id, mode, target_temperature=temp
            )
            self.async_write_ha_state()
            # Request fresh data from coordinator to update UI
            await self.coordinator.async_request_refresh()
        except FenixControlError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="api_error_set_temperature",
            ) from err
        # The temperature command already selects manual (heat) mode
        if hvac_mode is not None and hvac_mode != HVACMode.HEAT:
            await self.async_set_hvac_mode(hvac_mode)

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
            await self._client.set_preset_mode(self._device_id, preset_value)
            _LOGGER.info(
                "HVAC mode set successfully for device %s: %s",
                self._device_id,
                hvac_mode,
            )
        except FenixControlError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="api_error_set_hvac_mode",
            ) from err

        # Update coordinator with optimistic data for immediate UI feedback
        self.coordinator.update_device_preset_mode(self._device_id, preset_value)
        # Force entity state update in Home Assistant
        self.async_write_ha_state()

    async def async_handle_set_preset_mode_service(self, preset_mode: str) -> None:
        """Handle preset mode service calls with backward-compatible aliases."""
        normalized_preset = preset_mode.lower()
        canonical_preset = PRESET_CANONICAL_MAP.get(normalized_preset, preset_mode)
        await super().async_handle_set_preset_mode_service(canonical_preset)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode for special operations."""
        if self._is_holiday_active():
            _LOGGER.warning(
                "Preset mode change blocked for device %s: holiday mode active",
                self._device_id,
            )
            msg = HOLIDAY_LOCKED_MSG
            raise HomeAssistantError(msg)

        normalized_preset = preset_mode.lower()
        if normalized_preset not in self._normalized_preset_modes:
            _LOGGER.warning(
                "Unsupported preset mode for device %s: %s (valid: %s)",
                self._device_id,
                preset_mode,
                sorted(self._normalized_preset_modes),
            )
            return

        # Convert preset mode string to device value
        preset_value = PRESET_INVERTED[normalized_preset]
        _LOGGER.debug(
            "Setting preset mode for device %s: %s (preset_mode=%s)",
            self._device_id,
            preset_mode,
            preset_value,
        )

        try:
            # Send preset mode change to device
            await self._client.set_preset_mode(self._device_id, preset_value)
            _LOGGER.info(
                "Preset mode set successfully for device %s: %s",
                self._device_id,
                preset_mode,
            )
        except FenixControlError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="api_error_set_preset_mode",
            ) from err

        # Update coordinator with optimistic data and force state update
        self.coordinator.update_device_preset_mode(self._device_id, preset_value)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Request latest data from coordinator (called by Home Assistant)."""
        await self.coordinator.async_request_refresh()
