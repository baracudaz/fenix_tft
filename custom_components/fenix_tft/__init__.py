"""Fenix TFT Home Assistant integration package."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, TypedDict

import voluptuous as vol
from homeassistant.components.persistent_notification import async_create
from homeassistant.components.recorder.statistics import async_add_external_statistics
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
    ATTR_DAYS_BACK,
    ATTR_END_DATE,
    ATTR_ENERGY_ENTITY,
    ATTR_MODE,
    ATTR_START_DATE,
    DOMAIN,
    HOLIDAY_MODE_DEFROST,
    HOLIDAY_MODE_OFF,
    HOLIDAY_MODE_REDUCE,
    HOLIDAY_MODE_SUNDAY,
    HOLIDAY_PROPAGATION_DELAY,
    PLATFORMS,
    SERVICE_CANCEL_HOLIDAY_SCHEDULE,
    SERVICE_IMPORT_HISTORICAL_STATISTICS,
    SERVICE_SET_HOLIDAY_SCHEDULE,
)
from .coordinator import FenixTFTCoordinator
from .statistics import (
    convert_energy_api_data_to_statistics,
    create_energy_statistic_metadata,
    get_first_statistic_time,
    get_last_statistic_sum,
)


class FenixTFTRuntimeData(TypedDict):
    """Runtime data for Fenix TFT integration."""

    api: FenixTFTApi
    coordinator: FenixTFTCoordinator


type FenixTFTConfigEntry = ConfigEntry[FenixTFTRuntimeData]

_LOGGER = logging.getLogger(__name__)

# Aggregation thresholds for dynamic period selection
HOURLY_AGGREGATION_MAX_DAYS = 7  # Use hourly for last 7 days
DAILY_AGGREGATION_MAX_DAYS = 90  # Use daily up to 90 days back
DAILY_AGGREGATION_CHUNK_DAYS = 30  # Max days are included in each daily API call
MONTHLY_AGGREGATION_MAX_DAYS = 365  # Use monthly beyond 90 days back

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

SERVICE_IMPORT_HISTORICAL_STATISTICS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENERGY_ENTITY): cv.entity_id,
        vol.Required(ATTR_DAYS_BACK): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=365)
        ),
    }
)


def _get_installation_from_entity(
    hass: HomeAssistant, entity_id: str
) -> tuple[ConfigEntry | None, str | None, str | None]:
    """
    Resolve installation context for an entity via registries.

    Early returns handle missing data; uses named expressions for brevity.
    """
    entity_reg = er.async_get(hass)
    if not (entity_entry := entity_reg.async_get(entity_id)):
        return None, None, None

    entry = hass.config_entries.async_get_entry(entity_entry.config_entry_id)
    if entry is None or entry.state is not ConfigEntryState.LOADED:
        return None, None, None

    device_reg = dr.async_get(hass)
    device_entry = (
        device_reg.async_get(entity_entry.device_id) if entity_entry.device_id else None
    )
    if device_entry is None:
        return None, None, None

    device_id = next(
        (
            identifier[1]
            for identifier in device_entry.identifiers
            if identifier[0] == DOMAIN
        ),
        None,
    )
    if device_id is None:
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
    if matched is None:
        return None, None, None
    return entry, matched.get("installation_id"), matched.get("installation")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:  # noqa: ARG001, C901, PLR0915
    """Set up the Fenix TFT integration and register services."""

    async def async_set_holiday_schedule(call: ServiceCall) -> None:
        """Handle set_holiday_schedule service call."""
        entity_id = call.data[ATTR_ENTITY_ID]
        # Convert provided datetimes to local timezone expected by API
        start_date_input = call.data[ATTR_START_DATE]
        end_date_input = call.data[ATTR_END_DATE]

        # Treat naive datetimes as local, convert aware datetimes to local
        start_date = (
            start_date_input
            if start_date_input.tzinfo is None
            else dt_util.as_local(start_date_input)
        )
        end_date = (
            end_date_input
            if end_date_input.tzinfo is None
            else dt_util.as_local(end_date_input)
        )
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
        await asyncio.sleep(HOLIDAY_PROPAGATION_DELAY)

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
        await asyncio.sleep(HOLIDAY_PROPAGATION_DELAY)

        # Refresh coordinator to reflect changes
        coordinator = config_entry.runtime_data["coordinator"]
        await coordinator.async_refresh()

        _LOGGER.info(
            "Holiday schedule canceled for installation %s (%s)",
            installation_name,
            installation_id,
        )

    async def async_import_historical_statistics(call: ServiceCall) -> None:  # noqa: PLR0912, PLR0915
        """Handle import_historical_statistics service call."""
        energy_entity_id = call.data[ATTR_ENERGY_ENTITY]
        days_back = call.data[ATTR_DAYS_BACK]

        entity_id = energy_entity_id
        entity_reg = er.async_get(hass)
        if not (entity_entry := entity_reg.async_get(entity_id)):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entity_not_found",
                translation_placeholders={"entity_id": entity_id},
            )

        config_entry = hass.config_entries.async_get_entry(entity_entry.config_entry_id)
        if config_entry is None or config_entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="integration_not_loaded",
            )

        device_reg = dr.async_get(hass)
        device_entry = (
            device_reg.async_get(entity_entry.device_id)
            if entity_entry.device_id
            else None
        )
        if device_entry is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_found",
            )

        device_id = next(
            (
                identifier[1]
                for identifier in device_entry.identifiers
                if identifier[0] == DOMAIN
            ),
            None,
        )
        if device_id is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_id_missing",
            )

        # Get device data from coordinator
        coordinator = config_entry.runtime_data["coordinator"]
        device_data = next(
            (d for d in coordinator.data if d.get("id") == device_id),
            None,
        )
        if device_data is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_data_not_found",
            )

        room_id = device_data.get("room_id")
        installation_id = device_data.get("installation_id")
        device_name = device_data.get("name", "Unknown Device")

        if not room_id or not installation_id:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="room_installation_missing",
            )

        # Get the statistic ID for this energy sensor
        entity_unique_part = (
            energy_entity_id.split(".", 1)[1]
            if "." in energy_entity_id
            else energy_entity_id
        )
        statistic_id = f"{DOMAIN}:{entity_unique_part}_imported"

        # Check if we have existing statistics
        first_stat_time = await get_first_statistic_time(hass, statistic_id)

        # Calculate date range based on existing statistics
        if first_stat_time:
            # Import data ending at first existing datapoint,
            # going back days_back from there
            _LOGGER.info(
                "Found existing statistics for %s starting at %s. "
                "Will import %d days before this timestamp.",
                device_name,
                first_stat_time,
                days_back,
            )
            end_date = first_stat_time
            start_date = end_date - dt_util.dt.timedelta(days=days_back)
            days_to_import = days_back
        else:
            # No existing statistics, import from now going back
            _LOGGER.info(
                "No existing statistics found for %s. Will import %d days from now.",
                device_name,
                days_back,
            )
            end_date = dt_util.now()
            start_date = end_date - dt_util.dt.timedelta(days=days_back)
            days_to_import = days_back

        # Create notification
        notification_id = f"fenix_import_{entity_id.replace('.', '_')}"
        import_msg = (
            f"Starting historical data import for {device_name}. "
            f"Importing {days_to_import} days of energy data"
        )
        if first_stat_time:
            import_msg += (
                f" (before existing data from {first_stat_time.strftime('%Y-%m-%d')})"
            )
        import_msg += ". This will take about a minute."

        async_create(
            hass,
            import_msg,
            title="Fenix TFT Historical Import",
            notification_id=notification_id,
        )

        _LOGGER.info(
            "Starting historical data import for device %s (%s days, energy)%s",
            device_name,
            days_to_import,
            f" before {first_stat_time}" if first_stat_time else "",
        )

        api = config_entry.runtime_data["api"]
        subscription_id = api.subscription_id
        if not subscription_id:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="missing_subscription_id",
                message=(
                    "Subscription ID is missing; cannot import historical data. "
                    "Please re-authenticate or check your account permissions."
                ),
            )

        _LOGGER.info("Starting dynamic aggregation import for %d days", days_back)

        try:
            # Import energy data
            if energy_entity_id:
                _LOGGER.debug("Importing energy statistics for %s", device_name)
                all_energy_data = []

                # Dynamic aggregation: work backwards from end_date
                # Last 7 days: Hour, 8-90 days ago: Day, 91+ days ago: Month
                current_date = end_date
                remaining_days = days_back

                while remaining_days > 0 and current_date > start_date:
                    # Determine period and chunk size based on how far back we are
                    days_from_now = (end_date - current_date).days

                    if days_from_now < HOURLY_AGGREGATION_MAX_DAYS:
                        # Recent data: use hourly aggregation
                        period = "Hour"
                        chunk_days = min(
                            HOURLY_AGGREGATION_MAX_DAYS - days_from_now,
                            remaining_days,
                        )
                    elif days_from_now < DAILY_AGGREGATION_MAX_DAYS:
                        # Medium range: use daily aggregation
                        period = "Day"
                        chunk_days = min(DAILY_AGGREGATION_CHUNK_DAYS, remaining_days)
                    else:
                        # Older data: use monthly aggregation
                        period = "Month"
                        chunk_days = min(MONTHLY_AGGREGATION_MAX_DAYS, remaining_days)

                    # Calculate chunk boundaries
                    chunk_end = current_date
                    chunk_start = max(
                        current_date - dt_util.dt.timedelta(days=chunk_days), start_date
                    )

                    _LOGGER.debug(
                        "Fetching energy (%s aggregation): %s to %s",
                        period,
                        chunk_start,
                        chunk_end,
                    )

                    try:
                        energy_data = await api.get_room_historical_energy(
                            installation_id,
                            room_id,
                            subscription_id,
                            chunk_start,
                            chunk_end,
                            period,
                        )
                        if energy_data:
                            all_energy_data.extend(energy_data)
                            _LOGGER.debug(
                                "Fetched %d energy data points (%s)",
                                len(energy_data),
                                period,
                            )
                        else:
                            _LOGGER.debug(
                                "No energy data available for period %s to %s",
                                chunk_start.date(),
                                chunk_end.date(),
                            )
                    except FenixTFTApiError as err:
                        _LOGGER.warning("Failed to fetch energy data chunk: %s", err)

                    # Move to next chunk
                    current_date = chunk_start
                    remaining_days -= chunk_days
                    await asyncio.sleep(1)  # Rate limiting

                if all_energy_data:
                    # Get entity friendly name from state which includes device name
                    energy_state = hass.states.get(energy_entity_id)
                    energy_entity_name = (
                        energy_state.name
                        if energy_state
                        else energy_entity_id.replace("_", " ").title()
                    )
                    energy_metadata = create_energy_statistic_metadata(
                        energy_entity_id, energy_entity_name
                    )

                    # Get last cumulative sum to continue from existing statistics
                    starting_sum = await get_last_statistic_sum(
                        hass, energy_metadata["statistic_id"]
                    )

                    # Convert all data at once to maintain cumulative sum
                    all_energy_stats = convert_energy_api_data_to_statistics(
                        all_energy_data, starting_sum
                    )
                    async_add_external_statistics(
                        hass, energy_metadata, all_energy_stats
                    )
                    _LOGGER.info(
                        "Imported %d energy statistics for %s",
                        len(all_energy_stats),
                        energy_entity_id,
                    )

            # Success notification
            async_create(
                hass,
                f"Successfully imported historical energy data for {device_name}. "
                f"Data is now available in the Energy Dashboard and history graphs.",
                title="Fenix TFT Historical Import Complete",
                notification_id=notification_id,
            )

        except Exception as err:
            _LOGGER.exception("Error during historical data import")
            async_create(
                hass,
                f"Failed to import historical data for {device_name}: {err}",
                title="Fenix TFT Historical Import Failed",
                notification_id=notification_id,
            )
            error_msg = f"Failed to import historical data for {device_name}: {err}"
            raise HomeAssistantError(error_msg) from err

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

    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_HISTORICAL_STATISTICS,
        async_import_historical_statistics,
        schema=SERVICE_IMPORT_HISTORICAL_STATISTICS_SCHEMA,
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
