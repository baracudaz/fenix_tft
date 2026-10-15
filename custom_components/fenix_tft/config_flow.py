"""Config flow for Fenix TFT integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import AbortFlow, FlowResult
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from pyfenixcontrol import (
    FenixControlAuthError,
    FenixControlError,
    PasswordAuth,
)

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication with Fenix TFT fails."""


class CannotConnectError(Exception):
    """Raised when the FENIX cloud cannot be reached."""


async def validate_input(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input."""
    _LOGGER.debug("Validating FENIX credentials")

    # A dedicated session keeps the identity server's login cookies away from
    # other config entries and integrations. It shares Home Assistant's
    # connector, so it is detached (not closed) once the login is validated.
    session = async_create_clientsession(hass, auto_cleanup=False)
    auth = PasswordAuth(session, user_input[CONF_USERNAME], user_input[CONF_PASSWORD])

    try:
        await auth.async_login()
    except FenixControlAuthError as err:
        # Expected user error, shown in the form; no need to log it louder
        _LOGGER.debug("FENIX login rejected: %s", err)
        raise AuthenticationError from err
    except FenixControlError as err:
        _LOGGER.debug("Cannot connect to the FENIX cloud: %s", err)
        raise CannotConnectError from err
    finally:
        session.detach()

    _LOGGER.debug("FENIX login successful")

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
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_USERNAME], data=info
                )
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except AbortFlow:
                raise
            except Exception:
                _LOGGER.exception("Unexpected config flow error")
                errors["base"] = "unknown"

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

    async def async_step_reauth(self, _: dict[str, Any]) -> FlowResult:
        """Handle reauthentication flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauthentication confirmation."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates=user_input,
                )
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except AbortFlow:
                raise
            except Exception:
                _LOGGER.exception("Unexpected reauthentication error")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME, default=reauth_entry.data[CONF_USERNAME]
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration flow (update credentials without removing entry)."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
                await self.async_set_unique_id(user_input[CONF_USERNAME])
                self._abort_if_unique_id_mismatch(reason="username_exists")
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    data_updates=user_input,
                )
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except AbortFlow:
                raise
            except Exception:
                _LOGGER.exception("Unexpected reconfiguration error")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USERNAME,
                        default=reconfigure_entry.data.get(CONF_USERNAME, ""),
                    ): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )
