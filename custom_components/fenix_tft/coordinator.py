"""Coordinator for Fenix TFT integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FenixTFTApi
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class FenixTFTCoordinator(DataUpdateCoordinator):
    """Data update coordinator for Fenix TFT."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: FenixTFTApi,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the Fenix TFT coordinator."""
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            config_entry=config_entry,
        )
        self.api = api

    async def _async_update_data(self):
        """Fetch data from Fenix TFT API."""
        try:
            return await self.api.get_devices()
        except Exception as err:
            raise UpdateFailed(f"Error fetching Fenix TFT data: {err}") from err
