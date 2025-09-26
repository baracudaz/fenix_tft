"""Config flow for Fenix TFT integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult  # Correct import

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class FenixTFTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fenix TFT."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_create_entry(
                title="Fenix TFT",
                data={
                    "access_token": user_input["access_token"],
                    "refresh_token": user_input["refresh_token"],
                },
            )

        data_schema = vol.Schema(
            {
                vol.Required("access_token"): str,
                vol.Required("refresh_token"): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return FenixTFTOptionsFlowHandler(config_entry)


class FenixTFTOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow handler for Fenix TFT."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow handler."""
        self.config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,  # noqa: ARG002 # not implemented yet
    ) -> FlowResult:
        """Handle options flow init step."""
        # user_input is unused because options are not yet implemented
        return self.async_create_entry(title="", data={})
