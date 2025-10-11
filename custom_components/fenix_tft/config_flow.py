"""Config flow for Fenix TFT integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FenixTFTApi
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication with Fenix TFT fails."""


async def validate_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input."""
    _LOGGER.debug("Validating input: username=%s", user_input[CONF_USERNAME])

    session = async_get_clientsession(hass)
    api = FenixTFTApi(session, user_input[CONF_USERNAME], user_input[CONF_PASSWORD])

    if not await api.login():
        _LOGGER.error("Authentication failed for username: %s", user_input[CONF_USERNAME])
        raise AuthenticationError

    _LOGGER.debug("Authentication successful for username: %s", user_input[CONF_USERNAME])

    return user_input


class FenixTFTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fenix TFT."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                # Optionally, set unique_id based on username or API user id
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_USERNAME], data=info)
            except AuthenticationError:
                _LOGGER.exception("Config flow authentication error")
                errors["base"] = "auth_failed"  # Add to strings.json
            except Exception:
                _LOGGER.exception("Unexpected config flow error")
                errors["base"] = "unknown"  # Add to strings.json

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
