"""Config flow for Fenix TFT integration."""

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FenixTFTApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, user_input: dict) -> dict:
    """Validate the user input."""
    _LOGGER.debug("Validating input: username=%s", user_input["username"])

    session = async_get_clientsession(hass)
    api = FenixTFTApi(session, user_input["username"], user_input["password"])

    if not await api.login():
        _LOGGER.error("Authentication failed for username: %s", user_input["username"])
        raise ValueError("Authentication failed")

    _LOGGER.debug("Authentication successful for username: %s", user_input["username"])

    return user_input


class FenixTFTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fenix TFT."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=user_input["username"], data=info)
            except ValueError as err:
                _LOGGER.error("Config flow error: %s", err)
                errors["base"] = (
                    "auth_failed" if str(err) == "Authentication failed" else "unknown"
                )
            except Exception as err:
                _LOGGER.error("Unexpected config flow error: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("username"): str,
                    vol.Required("password"): str,
                }
            ),
            errors=errors,
        )
