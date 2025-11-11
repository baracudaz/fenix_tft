"""Fenix TFT Home Assistant integration package."""

import logging
from datetime import datetime
from typing import TypedDict

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import FenixTFTApi, FenixTFTApiError
from .const import DOMAIN, PLATFORMS
from .coordinator import FenixTFTCoordinator


class FenixTFTRuntimeData(TypedDict):
    """Runtime data for Fenix TFT integration."""

    api: FenixTFTApi
    coordinator: FenixTFTCoordinator


type FenixTFTConfigEntry = ConfigEntry[FenixTFTRuntimeData]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: FenixTFTConfigEntry) -> bool:
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
    entry.runtime_data = FenixTFTRuntimeData(
        api=api,
        coordinator=coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services for holiday schedule management
    await async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: FenixTFTConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Remove runtime_data on unload
        entry.runtime_data = None
    return unload_ok


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Fenix TFT integration."""
    from datetime import datetime  # noqa: PLC0415

    import voluptuous as vol  # noqa: PLC0415

    from homeassistant.exceptions import (  # noqa: PLC0415
        HomeAssistantError,
        ServiceValidationError,
    )
    from homeassistant.helpers import config_validation as cv  # noqa: PLC0415
    from homeassistant.util import dt as dt_util  # noqa: PLC0415

    from .const import DOMAIN  # noqa: PLC0415

    # Service schema for setting holiday schedule
    SET_HOLIDAY_SCHEMA = vol.Schema(
        {
            vol.Required("installation_id"): cv.string,
            vol.Required("start_time"): cv.datetime,
            vol.Required("end_time"): cv.datetime,
            vol.Required("mode"): vol.In([1, 2, 5, 8]),
        }
    )

    # Service schema for canceling holiday schedule
    CANCEL_HOLIDAY_SCHEMA = vol.Schema(
        {
            vol.Required("installation_id"): cv.string,
        }
    )

    async def async_set_holiday_schedule(call: "ServiceCall") -> None:
        """Handle set_holiday_schedule service call."""
        installation_id = call.data["installation_id"]
        start_time: datetime = call.data["start_time"]
        end_time: datetime = call.data["end_time"]
        mode: int = call.data["mode"]

        # Validate times
        if end_time <= start_time:
            raise ServiceValidationError(
                "End time must be after start time",
                translation_domain=DOMAIN,
                translation_key="invalid_time_range",
            )

        # Find a config entry to use the API
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError(
                "No Fenix TFT integration configured",
                translation_domain=DOMAIN,
                translation_key="no_integration",
            )

        entry: FenixTFTConfigEntry = entries[0]
        api: FenixTFTApi = entry.runtime_data["api"]

        try:
            await api.set_holiday_schedule(installation_id, start_time, end_time, mode)
            # Refresh coordinator to update states
            coordinator: FenixTFTCoordinator = entry.runtime_data["coordinator"]
            await coordinator.async_request_refresh()
        except FenixTFTApiError as err:
            raise HomeAssistantError(
                f"Failed to set holiday schedule: {err}",
                translation_domain=DOMAIN,
                translation_key="api_error",
            ) from err

    async def async_cancel_holiday_schedule(call: "ServiceCall") -> None:
        """Handle cancel_holiday_schedule service call."""
        installation_id = call.data["installation_id"]

        # Find a config entry to use the API
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            raise ServiceValidationError(
                "No Fenix TFT integration configured",
                translation_domain=DOMAIN,
                translation_key="no_integration",
            )

        entry: FenixTFTConfigEntry = entries[0]
        api: FenixTFTApi = entry.runtime_data["api"]

        try:
            await api.cancel_holiday_schedule(installation_id)
            # Refresh coordinator to update states
            coordinator: FenixTFTCoordinator = entry.runtime_data["coordinator"]
            await coordinator.async_request_refresh()
        except FenixTFTApiError as err:
            raise HomeAssistantError(
                f"Failed to cancel holiday schedule: {err}",
                translation_domain=DOMAIN,
                translation_key="api_error",
            ) from err

    # Register services (only once)
    if not hass.services.has_service(DOMAIN, "set_holiday_schedule"):
        hass.services.async_register(
            DOMAIN,
            "set_holiday_schedule",
            async_set_holiday_schedule,
            schema=SET_HOLIDAY_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, "cancel_holiday_schedule"):
        hass.services.async_register(
            DOMAIN,
            "cancel_holiday_schedule",
            async_cancel_holiday_schedule,
            schema=CANCEL_HOLIDAY_SCHEMA,
        )
