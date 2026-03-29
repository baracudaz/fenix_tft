"""Coordinator for Fenix TFT integration."""

import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FenixTFTApi, FenixTFTApiError, FenixTFTAuthError
from .const import (
    DOMAIN,
    HVAC_ACTION_HEATING,
    HVAC_ACTION_IDLE,
    HVAC_ACTION_OFF,
    OPTIMISTIC_UPDATE_DURATION,
    POLLING_INTERVAL,
    PRESET_MODE_OFF,
)

CONSECUTIVE_FAILURES_BEFORE_ISSUE = 3

_LOGGER = logging.getLogger(__name__)


def _predict_hvac_action(
    preset_mode: int,
    target_temp: float | None = None,
    current_temp: float | None = None,
) -> int:
    """
    Predict hvac_action based on preset_mode and temperatures.

    - PRESET_MODE_OFF → HVAC_ACTION_OFF
    - Active mode with target > current → HVAC_ACTION_HEATING (device likely heating)
    - Active mode otherwise → HVAC_ACTION_IDLE (safe default)
    """
    if preset_mode == PRESET_MODE_OFF:
        return HVAC_ACTION_OFF
    if (
        target_temp is not None
        and current_temp is not None
        and target_temp > current_temp
    ):
        return HVAC_ACTION_HEATING
    return HVAC_ACTION_IDLE


class FenixTFTCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Data update coordinator for Fenix TFT."""

    api: FenixTFTApi
    _optimistic_updates: dict[str, tuple[int, int, float]]
    _consecutive_failures: int

    def __init__(
        self, hass: HomeAssistant, api: FenixTFTApi, config_entry: ConfigEntry
    ) -> None:
        """Initialize the Fenix TFT coordinator with fixed polling interval."""
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLLING_INTERVAL),
            config_entry=config_entry,
        )
        self.api = api
        self._optimistic_updates: dict[str, tuple[int, int, float]] = {}
        self._consecutive_failures: int = 0

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch data from Fenix TFT API."""
        _LOGGER.debug("Starting coordinator data update")
        try:
            fresh_data: list[
                dict[str, Any]
            ] = await self.api.fetch_devices_with_energy_data()
            _LOGGER.debug(
                "Coordinator data update successful: fetched %d device(s)",
                len(fresh_data) if fresh_data else 0,
            )
        except FenixTFTAuthError as err:
            _LOGGER.exception("Authentication failure during coordinator update")
            raise ConfigEntryAuthFailed(str(err)) from err
        except (TimeoutError, FenixTFTApiError, aiohttp.ClientError) as err:
            self._consecutive_failures += 1
            _LOGGER.exception(
                "Coordinator data update failed (consecutive failures: %d)",
                self._consecutive_failures,
            )
            if self._consecutive_failures >= CONSECUTIVE_FAILURES_BEFORE_ISSUE:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    "coordinator_unavailable",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="coordinator_unavailable",
                    translation_placeholders={
                        "consecutive_failures": str(self._consecutive_failures),
                    },
                )
            msg = f"Error fetching Fenix TFT data: {err}"
            raise UpdateFailed(msg) from err

        if self._consecutive_failures >= CONSECUTIVE_FAILURES_BEFORE_ISSUE:
            ir.async_delete_issue(self.hass, DOMAIN, "coordinator_unavailable")
        self._consecutive_failures = 0

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
            _LOGGER.debug(
                "Optimistic update expired for device %s, reverting to fresh data",
                device_id,
            )
            del self._optimistic_updates[device_id]

        if expired_updates:
            _LOGGER.debug(
                "Removed %d expired optimistic update(s)", len(expired_updates)
            )

        return fresh_data

    def update_device_preset_mode(self, device_id: str, preset_mode: int) -> None:
        """Optimistically update device preset mode in coordinator data."""
        if not self.data:
            _LOGGER.warning(
                "Cannot apply optimistic update for device %s: no coordinator data",
                device_id,
            )
            return

        device_found = False
        for device in self.data:
            if device.get("id") == device_id:
                target_temp: float | None = device.get("target_temp")
                current_temp: float | None = device.get("current_temp")
                predicted_hvac_action: int = _predict_hvac_action(
                    preset_mode, target_temp, current_temp
                )
                current_time: float = self.hass.loop.time()
                self._optimistic_updates[device_id] = (
                    preset_mode,
                    predicted_hvac_action,
                    current_time,
                )
                device["preset_mode"] = preset_mode
                device["hvac_action"] = predicted_hvac_action
                device_found = True
                _LOGGER.debug(
                    "Optimistic update applied for device %s: preset_mode=%s, "
                    "predicted_hvac_action=%s (target=%.1f, current=%.1f)",
                    device_id,
                    preset_mode,
                    predicted_hvac_action,
                    target_temp if target_temp is not None else float("nan"),
                    current_temp if current_temp is not None else float("nan"),
                )
                break

        if not device_found:
            _LOGGER.warning(
                "Device %s not found in coordinator data for optimistic update",
                device_id,
            )

    @property
    def pending_optimistic_update_count(self) -> int:
        """Return the number of devices with pending optimistic updates."""
        return len(self._optimistic_updates)

    # Adaptive polling removed: fixed update_interval is used.
