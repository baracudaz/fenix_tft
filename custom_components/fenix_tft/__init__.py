"""Fenix TFT Home Assistant integration package."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, TypedDict

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, ServiceCall

from .api import FenixTFTApi, FenixTFTApiError
from .const import (
    ATTR_END_DATE,
    ATTR_MODE,
    ATTR_START_DATE,
    DOMAIN,
    HOLIDAY_MODE_DEFROST,
    HOLIDAY_MODE_OFF,
    HOLIDAY_MODE_REDUCE,
    HOLIDAY_MODE_SUNDAY,
    PLATFORMS,
    SERVICE_CANCEL_HOLIDAY_SCHEDULE,
    SERVICE_SET_HOLIDAY_SCHEDULE,
)
from .coordinator import FenixTFTCoordinator


class FenixTFTRuntimeData(TypedDict):
    """Runtime data for Fenix TFT integration."""

    api: FenixTFTApi
    coordinator: FenixTFTCoordinator


type FenixTFTConfigEntry = ConfigEntry[FenixTFTRuntimeData]

_LOGGER = logging.getLogger(__name__)

# Valid holiday modes for service
VALID_HOLIDAY_MODES = {
    "off": HOLIDAY_MODE_OFF,
    "reduce": HOLIDAY_MODE_REDUCE,
    "defrost": HOLIDAY_MODE_DEFROST,
    "sunday": HOLIDAY_MODE_SUNDAY,
}

# Service schemas
SET_HOLIDAY_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required(ATTR_START_DATE): cv.datetime,
        vol.Required(ATTR_END_DATE): cv.datetime,
        vol.Required(ATTR_MODE): vol.In(VALID_HOLIDAY_MODES.keys()),
    }
)

CANCEL_HOLIDAY_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
    }
)


def _get_installation_from_entity(
    hass: HomeAssistant, entity_id: str
) -> tuple[ConfigEntry | None, str | None, str | None]:
    """
    Get config entry, installation ID, and name from entity ID.

    Returns:
        Tuple of (config_entry, installation_id, installation_name)
        or (None, None, None) if not found

    """
    # Get entity from registry to find associated device
    entity_reg = er.async_get(hass)
    entity_entry = entity_reg.async_get(entity_id)

    if not entity_entry:
        return None, None, None

    # Find the config entry
    entry = hass.config_entries.async_get_entry(entity_entry.config_entry_id)
    if not entry or entry.state is not ConfigEntryState.LOADED:
        return None, None, None

    # Get installation from coordinator data
    coordinator = entry.runtime_data["coordinator"]
    for device in coordinator.data:
        # Match by device name from entity's original_name or device_id
        if device.get("installation_id"):
            return entry, device.get("installation_id"), device.get("installation")

    return None, None, None


async def async_setup(hass: HomeAssistant, config: dict) -> bool:  # noqa: ARG001
    """Set up the Fenix TFT integration and register services."""

    async def async_set_holiday_schedule(call: ServiceCall) -> None:
        """Handle set_holiday_schedule service call."""
        entity_id = call.data[ATTR_ENTITY_ID]
        start_date = call.data[ATTR_START_DATE]
        end_date = call.data[ATTR_END_DATE]
        mode_name: str = call.data[ATTR_MODE]
        # Validate dates
        if end_date <= start_date:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="end_date_before_start",
            )

        # Get installation from entity
        config_entry, installation_id, installation_name = (
            _get_installation_from_entity(hass, entity_id)
        )

        if not config_entry:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entity_not_found",
                translation_placeholders={"entity_id": entity_id},
            )

        if not installation_id:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="installation_id_missing",
            )

        # Get mode code
        mode_code = VALID_HOLIDAY_MODES[mode_name]

        # Call API
        api = config_entry.runtime_data["api"]
        try:
            await api.set_holiday_schedule(
                installation_id, start_date, end_date, mode_code
            )
        except FenixTFTApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="api_error_set_holiday",
            ) from err

        # Wait for backend to process the holiday schedule change
        # The Fenix backend needs time to propagate changes to devices
        await asyncio.sleep(5)

        # Refresh coordinator to reflect changes
        coordinator = config_entry.runtime_data["coordinator"]
        await coordinator.async_refresh()

        _LOGGER.info(
            "Holiday schedule set for installation %s (%s): %s to %s, mode %s",
            installation_name,
            installation_id,
            start_date,
            end_date,
            mode_name,
        )

    async def async_cancel_holiday_schedule(call: ServiceCall) -> None:
        """Handle cancel_holiday_schedule service call."""
        entity_id = call.data[ATTR_ENTITY_ID]

        # Get installation from entity
        config_entry, installation_id, installation_name = (
            _get_installation_from_entity(hass, entity_id)
        )

        if not config_entry:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entity_not_found",
                translation_placeholders={"entity_id": entity_id},
            )

        if not installation_id:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="installation_id_missing",
            )

        # Call API
        api = config_entry.runtime_data["api"]
        try:
            await api.cancel_holiday_schedule(installation_id)
        except FenixTFTApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="api_error_cancel_holiday",
            ) from err

        # Wait for backend to process the cancellation
        # The Fenix backend needs time to propagate changes to devices
        await asyncio.sleep(5)

        # Refresh coordinator to reflect changes
        coordinator = config_entry.runtime_data["coordinator"]
        await coordinator.async_refresh()

        _LOGGER.info(
            "Holiday schedule canceled for installation %s (%s)",
            installation_name,
            installation_id,
        )

    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_HOLIDAY_SCHEDULE,
        async_set_holiday_schedule,
        schema=SET_HOLIDAY_SCHEDULE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_HOLIDAY_SCHEDULE,
        async_cancel_holiday_schedule,
        schema=CANCEL_HOLIDAY_SCHEDULE_SCHEMA,
    )

    return True


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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FenixTFTConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Remove runtime_data on unload
        entry.runtime_data = None
    return unload_ok
