"""Coordinator for Fenix TFT integration."""

import logging
from datetime import timedelta
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FenixTFTApi
from .const import (
    DOMAIN,
    ERROR_BACKOFF_SECONDS,
    FAST_POLL_SECONDS,
    HVAC_ACTION_HEATING,
    SCAN_INTERVAL,
    SLOW_POLL_SECONDS,
    STARTUP_FAST_PERIOD,
)

_LOGGER = logging.getLogger(__name__)

OPTIMISTIC_UPDATE_DURATION: Final[int] = 10  # seconds


def _predict_hvac_action(preset_mode: int) -> int:
    """
    Predict hvac_action based on preset_mode.

    Based on typical thermostat behavior:
    - preset_mode 0 (off): hvac_action should be 2 (OFF)
    - preset_mode 1 (manual): hvac_action should be 0 (IDLE) or 1 (HEATING)
    - preset_mode 2 (program): hvac_action should be 0 (IDLE) or 1 (HEATING)
    - For active modes, we predict IDLE as a safe default
    """
    if preset_mode == 0:
        return 2  # OFF
    return 0  # IDLE


class FenixTFTCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Data update coordinator for Fenix TFT."""

    api: FenixTFTApi
    _optimistic_updates: dict[str, tuple[int, int, float]]

    def __init__(
        self, hass: HomeAssistant, api: FenixTFTApi, config_entry: ConfigEntry
    ) -> None:
        """
        Initialize the Fenix TFT coordinator.

        The initial update interval is set to the faster polling cadence. It
        will be adaptively increased/decreased after each successful refresh.
        """
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            # Start fast; will adapt post-refresh
            update_interval=timedelta(seconds=min(SCAN_INTERVAL, FAST_POLL_SECONDS)),
            config_entry=config_entry,
        )
        self.api = api
        self._optimistic_updates: dict[str, tuple[int, int, float]] = {}
        self._startup_time: float = hass.loop.time()
        self._error_backoff_until: float | None = None

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch data from Fenix TFT API."""
        try:
            fresh_data: list[dict[str, Any]] = await self.api.get_devices()
        except Exception as err:  # Broad allowed: external I/O layer
            # Enter temporary backoff window - we do not expose user setting but
            # reduce load automatically after repeated failures.
            self._error_backoff_until = self.hass.loop.time() + ERROR_BACKOFF_SECONDS
            self._set_update_interval(ERROR_BACKOFF_SECONDS)
            msg = f"Error fetching Fenix TFT data: {err}"
            raise UpdateFailed(msg) from err

        current_time: float = self.hass.loop.time()
        expired_updates: list[str] = []

        for device_id, (preset_mode, hvac_action, timestamp) in list(
            self._optimistic_updates.items()
        ):
            if current_time - timestamp > OPTIMISTIC_UPDATE_DURATION:
                expired_updates.append(device_id)
                continue
            for device in fresh_data:
                if device.get("id") == device_id:
                    _LOGGER.debug(
                        "Preserving optimistic update for device %s: "
                        "preset_mode=%s, hvac_action=%s",
                        device_id,
                        preset_mode,
                        hvac_action,
                    )
                    device["preset_mode"] = preset_mode
                    device["hvac_action"] = hvac_action
                    break

        for device_id in expired_updates:
            del self._optimistic_updates[device_id]

        # Decide new interval based on device activity / startup / backoff
        self._adapt_polling_interval(fresh_data)
        return fresh_data

    def update_device_preset_mode(self, device_id: str, preset_mode: int) -> None:
        """Optimistically update device preset mode in coordinator data."""
        if not self.data:
            return

        predicted_hvac_action: int = _predict_hvac_action(preset_mode)
        current_time: float = self.hass.loop.time()
        self._optimistic_updates[device_id] = (
            preset_mode,
            predicted_hvac_action,
            current_time,
        )

        for device in self.data:
            if device.get("id") == device_id:
                device["preset_mode"] = preset_mode
                device["hvac_action"] = predicted_hvac_action
                _LOGGER.debug(
                    "Optimistically updated device %s: preset_mode=%s, hvac_action=%s",
                    device_id,
                    preset_mode,
                    predicted_hvac_action,
                )
                break

    # ---------------------------------------------------------------------
    # Adaptive polling helpers
    # ---------------------------------------------------------------------
    def _adapt_polling_interval(self, devices: list[dict[str, Any]]) -> None:
        """
        Adapt polling interval based on runtime conditions.

        Rules (in order):
        1. Remain in backoff interval while error backoff active.
        2. Poll fast during initial startup period.
        3. Poll fast if any device is actively heating.
        4. Otherwise poll slow.
        Interval bounded between FAST_POLL_SECONDS and
        max(SCAN_INTERVAL, SLOW_POLL_SECONDS).
        """
        now = self.hass.loop.time()
        if self._error_backoff_until and now < self._error_backoff_until:
            # Still in backoff; do not change interval here.
            return

        in_startup = (now - self._startup_time) < STARTUP_FAST_PERIOD
        any_heating = any(
            dev.get("hvac_action") == HVAC_ACTION_HEATING for dev in devices
        )

        if in_startup or any_heating:
            desired = FAST_POLL_SECONDS
        else:
            desired = max(SCAN_INTERVAL, SLOW_POLL_SECONDS)

        # Only apply if changed to limit churn.
        current = (
            int(self.update_interval.total_seconds()) if self.update_interval else None
        )
        if current != desired:
            self._set_update_interval(desired)

    def _set_update_interval(self, seconds: int) -> None:
        """Set new update interval and log change."""
        self.update_interval = timedelta(seconds=seconds)
        _LOGGER.debug("Adaptive polling interval set to %s seconds", seconds)
