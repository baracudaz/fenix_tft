"""Fenix TFT Home Assistant integration package."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FenixTFTApi
from .const import DOMAIN, PLATFORMS
from .coordinator import FenixTFTCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fenix TFT from a config entry."""
    session = async_get_clientsession(hass)
    api = FenixTFTApi(session, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])

    coordinator = FenixTFTCoordinator(
        hass=hass,
        api=api,
        config_entry=entry,
    )

    await coordinator.async_config_entry_first_refresh()

    # Use runtime_data for Platinum quality scale compliance
    entry.runtime_data = {
        "api": api,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Remove runtime_data on unload
        entry.runtime_data = None
    return unload_ok
