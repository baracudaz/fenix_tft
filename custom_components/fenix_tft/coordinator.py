"""Coordinator for Fenix TFT integration."""

import logging
from datetime import timedelta
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FenixTFTApi
from .const import DOMAIN, SCAN_INTERVAL

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
        """Initialize the Fenix TFT coordinator."""
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
            config_entry=config_entry,
        )
        self.api = api
        self._optimistic_updates: dict[str, tuple[int, int, float]] = {}

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch data from Fenix TFT API."""
        try:
            fresh_data: list[dict[str, Any]] = await self.api.get_devices()
        except Exception as err:
            msg = f"Error fetching Fenix TFT data: {err}"
            raise UpdateFailed(msg) from err

        current_time: float = self.hass.loop.time()
        expired_updates: list[str] = []

        for device_id, (
            preset_mode,
            hvac_action,
            timestamp,
        ) in self._optimistic_updates.items():
            if current_time - timestamp > OPTIMISTIC_UPDATE_DURATION:
                expired_updates.append(device_id)
            else:
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
