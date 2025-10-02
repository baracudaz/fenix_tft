"""Config flow for Fenix TFT integration."""

import logging

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .api import FenixTFTApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, user_input: dict) -> dict:
    """Validate the user input."""
    _LOGGER.debug("Validating input: username=%s", user_input["username"])
    async with aiohttp.ClientSession() as session:
        api = FenixTFTApi(session, user_input["username"], user_input["password"])
        if not await api.login():
            _LOGGER.error(
                "Authentication failed for username: %s", user_input["username"]
            )
            raise ValueError("Authentication failed")

        if not api._sub or not api._access_token or not api._refresh_token:
            _LOGGER.error(
                "Missing sub or tokens after login: sub=%s, access_token=%s, refresh_token=%s",
                api._sub,
                api._access_token,
                api._refresh_token,
            )
            raise ValueError("Incomplete login response")

        return {
            "username": user_input["username"],
            "password": user_input["password"],
            "access_token": api._access_token,
            "refresh_token": api._refresh_token,
            "token_expires": api._token_expires,
            "sub": api._sub,
        }


class FenixTFTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fenix TFT."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                _LOGGER.debug("Config entry created: %s", info)
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
