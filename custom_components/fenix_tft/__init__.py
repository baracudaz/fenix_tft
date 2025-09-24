import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, PLATFORMS
from .api import FenixTFTApi

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    session = async_get_clientsession(hass)

    access_token = entry.data["access_token"]
    refresh_token = entry.data["refresh_token"]

    api = FenixTFTApi(session, access_token, refresh_token)

    # Ensure we fetch the user sub right away
    userinfo = await api.get_userinfo()
    _LOGGER.info("Logged in as %s", userinfo.get("email"))

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"api": api}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
