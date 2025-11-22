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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

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
    Resolve installation context for a given entity.

    Uses the entity registry to find the entity's device, then matches that
    device identifier against coordinator data to return the correct installation.
    """
    entity_reg = er.async_get(hass)
    entity_entry = entity_reg.async_get(entity_id)
    if not entity_entry:
        return None, None, None

    entry = hass.config_entries.async_get_entry(entity_entry.config_entry_id)
    if not entry or entry.state is not ConfigEntryState.LOADED:
        return None, None, None

    # Get device registry entry to obtain our (DOMAIN, device_id) identifier
    device_reg = dr.async_get(hass)
    device_entry = (
        device_reg.async_get(entity_entry.device_id) if entity_entry.device_id else None
    )
    if not device_entry:
        return None, None, None

    # Extract device_id from identifiers
    device_id = next(
        (
            identifier[1]
            for identifier in device_entry.identifiers
            if identifier[0] == DOMAIN
        ),
        None,
    )
    if not device_id:
        return None, None, None

    coordinator = entry.runtime_data["coordinator"]
    matched = next(
        (
            d
            for d in coordinator.data
            if d.get("id") == device_id and d.get("installation_id")
        ),
        None,
    )
    if not matched:
        return None, None, None
    return entry, matched.get("installation_id"), matched.get("installation")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:  # noqa: ARG001
    """Set up the Fenix TFT integration and register services."""

    async def async_set_holiday_schedule(call: ServiceCall) -> None:
        """Handle set_holiday_schedule service call."""
        entity_id = call.data[ATTR_ENTITY_ID]
        # Convert provided datetimes to local timezone expected by API
        start_date_utc = call.data[ATTR_START_DATE]
        end_date_utc = call.data[ATTR_END_DATE]
        start_date = dt_util.as_local(start_date_utc)
        end_date = dt_util.as_local(end_date_utc)
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
