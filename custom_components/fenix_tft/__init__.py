"""Fenix TFT Home Assistant integration package."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, TypedDict

import voluptuous as vol
from homeassistant.components.persistent_notification import async_create
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
)
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_PASSWORD,
    CONF_USERNAME,
    UnitOfEnergy,
)
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
    API_RATE_LIMIT_DELAY,
    ATTR_DAYS_BACK,
    ATTR_END_DATE,
    ATTR_ENERGY_ENTITY,
    ATTR_IMPORT_ALL_HISTORY,
    ATTR_MODE,
    ATTR_START_DATE,
    DOMAIN,
    HOLIDAY_PROPAGATION_DELAY,
    PLATFORMS,
    SERVICE_CANCEL_HOLIDAY_SCHEDULE,
    SERVICE_IMPORT_HISTORICAL_STATISTICS,
    SERVICE_SET_HOLIDAY_SCHEDULE,
    VALID_HOLIDAY_MODES,
)
from .coordinator import FenixTFTCoordinator
from .statistics import (
    convert_energy_api_data_to_statistics,
    create_energy_statistic_metadata,
    get_first_statistic_time,
)


class FenixTFTRuntimeData(TypedDict):
    """Runtime data stored in the config entry for the Fenix TFT integration."""

    api: FenixTFTApi
    coordinator: FenixTFTCoordinator


type FenixTFTConfigEntry = ConfigEntry[FenixTFTRuntimeData]

_LOGGER = logging.getLogger(__name__)

# Aggregation thresholds for dynamic period selection
HOURLY_AGGREGATION_MAX_DAYS = 7  # Use hourly for last 7 days
DAILY_AGGREGATION_MAX_DAYS = 90  # Use daily up to 90 days back
DAILY_AGGREGATION_CHUNK_DAYS = 30  # Max days are included in each daily API call
MONTHLY_AGGREGATION_MAX_DAYS = 365  # Use monthly beyond 90 days back
YEARLY_AGGREGATION_CHUNK_DAYS = 365  # Use yearly requests for very old data
FULL_HISTORY_BATCH_DAYS = 365  # Import "all history" in yearly chunks
FULL_HISTORY_EARLIEST_DATE = dt_util.dt.datetime(
    2000, 1, 1, tzinfo=dt_util.UTC
)  # Practical lower bound for progressive backfills

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
        vol.Optional(ATTR_DAYS_BACK, default=30): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=365)
        ),
        vol.Optional(ATTR_IMPORT_ALL_HISTORY, default=False): cv.boolean,
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


def _get_device_context_from_entity(
    hass: HomeAssistant, entity_id: str
) -> tuple[ConfigEntry, str, str, str, dict]:
    """
    Extract device context from entity for historical data import.

    Returns:
        Tuple of (config_entry, device_id, room_id, installation_id, device_data)

    Raises:
        ServiceValidationError: If any required context is missing

    """
    entity_reg = er.async_get(hass)
    entity_entry = entity_reg.async_get(entity_id)
    if not entity_entry:
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
        device_reg.async_get(entity_entry.device_id) if entity_entry.device_id else None
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

    if not room_id or not installation_id:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="room_installation_missing",
        )

    return config_entry, device_id, room_id, installation_id, device_data


def _calculate_import_date_range(
    days_back: int, first_stat_time: dt_util.dt.datetime | None
) -> tuple[dt_util.dt.datetime, dt_util.dt.datetime, int]:
    """
    Calculate the date range for historical data import.

    Since energy data points are day aggregates, we align imports to midnight
    boundaries to avoid overlaps and double-counting. All calculations are done
    in UTC to ensure consistency with the API and recorder.

    Args:
        days_back: Number of days to import (requested count)
        first_stat_time: Timestamp of first existing statistic (if any, in UTC)

    Returns:
        Tuple of (start_date_utc, end_date_utc, actual_days_imported)
        where dates are in UTC and actual_days reflects the real span

    """
    if first_stat_time:
        # Backfilling: import data ending at midnight (start of day) when
        # existing data begins. Since first_stat_time is in UTC from recorder,
        # convert to local to find the day boundary, then back to UTC.
        existing_day_start_local = dt_util.as_local(first_stat_time).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_date = dt_util.as_utc(existing_day_start_local)
    else:
        # No existing data: import up to midnight (start of today) in UTC
        # to avoid including today's data which the sensor is actively collecting
        today_midnight_local = dt_util.start_of_local_day()
        end_date = dt_util.as_utc(today_midnight_local)

    # Calculate start_date: go back days_back full days from end_date
    # This ensures we import exactly days_back days, not days_back + 1
    start_date = end_date - dt_util.dt.timedelta(days=days_back)

    # Calculate actual days imported (should match days_back for consistency)
    actual_days = (end_date - start_date).days

    return start_date, end_date, actual_days


def _calculate_import_end_date(
    first_stat_time: dt_util.dt.datetime | None,
) -> dt_util.dt.datetime:
    """Return the exclusive end boundary for historical imports."""
    if first_stat_time:
        existing_day_start_local = dt_util.as_local(first_stat_time).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return dt_util.as_utc(existing_day_start_local)

    return dt_util.as_utc(dt_util.start_of_local_day())


async def _import_energy_statistics_batch(  # noqa: PLR0913
    hass: HomeAssistant,
    energy_entity_id: str,
    energy_metadata: Any,
    statistic_id: str,
    energy_data: list[dict[str, object]],
    rebase_future_from: dt_util.dt.datetime | None,
) -> tuple[int, float, dt_util.dt.datetime | None, dt_util.dt.datetime | None]:
    """Convert and queue one imported batch of external statistics."""
    energy_stats = convert_energy_api_data_to_statistics(energy_data)
    if not energy_stats:
        return 0, 0.0, None, None

    async_add_external_statistics(hass, energy_metadata, energy_stats)
    imported_sum = float(energy_stats[-1]["sum"] or 0.0)

    if rebase_future_from and imported_sum > 0:
        get_instance(hass).async_adjust_statistics(
            statistic_id,
            rebase_future_from,
            imported_sum,
            UnitOfEnergy.WATT_HOUR,
        )

    _LOGGER.debug(
        "Queued %d imported statistic(s) for '%s' (sum %.2f Wh, rebase_from=%s)",
        len(energy_stats),
        energy_entity_id,
        imported_sum,
        rebase_future_from.isoformat() if rebase_future_from else None,
    )

    return (
        len(energy_stats),
        imported_sum,
        energy_stats[0]["start"],
        energy_stats[-1]["start"],
    )


def _determine_aggregation_period(
    days_back_from_reference: int, remaining_days: int
) -> tuple[str, int]:
    """
    Determine the aggregation period and chunk size based on how far back in time.

    Uses dynamic aggregation:
    - Last 7 days: hourly aggregation for detail
    - 8-90 days ago: daily aggregation
    - 91-365 days ago: monthly aggregation
    - 366+ days ago: yearly aggregation

    Args:
        days_back_from_reference: Number of days back from the latest import horizon
        remaining_days: Number of remaining days to process

    Returns:
        Tuple of (period, chunk_days) where period is "Hour", "Day", "Month",
        or "Year"

    """
    if days_back_from_reference < HOURLY_AGGREGATION_MAX_DAYS:
        # Recent data: use hourly aggregation
        period = "Hour"
        chunk_days = min(
            HOURLY_AGGREGATION_MAX_DAYS - days_back_from_reference,
            remaining_days,
        )
    elif days_back_from_reference < DAILY_AGGREGATION_MAX_DAYS:
        # Medium range: use daily aggregation
        period = "Day"
        chunk_days = min(DAILY_AGGREGATION_CHUNK_DAYS, remaining_days)
    elif days_back_from_reference < MONTHLY_AGGREGATION_MAX_DAYS:
        # Older data: use monthly aggregation
        period = "Month"
        chunk_days = min(MONTHLY_AGGREGATION_MAX_DAYS, remaining_days)
    else:
        # Very old data: use yearly aggregation to skip empty historical ranges fast
        period = "Year"
        chunk_days = min(YEARLY_AGGREGATION_CHUNK_DAYS, remaining_days)

    return period, chunk_days


async def _fetch_historical_energy_data(  # noqa: PLR0913
    api: FenixTFTApi,
    installation_id: str,
    room_id: str,
    subscription_id: str,
    start_date: dt_util.dt.datetime,
    end_date: dt_util.dt.datetime,
    days_back: int,
    device_name: str,
    aggregation_reference_end_date: dt_util.dt.datetime | None = None,
) -> list[dict]:
    """
    Fetch historical energy data with dynamic aggregation.

    Fetches data in chunks, using different aggregation periods based on age:
    - Recent data: hourly
    - Medium range: daily
    - Older data: monthly

    Args:
        api: Fenix TFT API instance
        installation_id: Installation ID
        room_id: Room ID
        subscription_id: Subscription ID
        start_date: Start date for data fetch
        end_date: End date for data fetch
        days_back: Total days to import
        device_name: Device name for logging
        aggregation_reference_end_date: Horizon to measure data age from when
            choosing Hour/Day/Month/Year aggregation. Defaults to ``end_date``.

    Returns:
        List of all fetched energy data points

    """
    _LOGGER.info(
        "Fetching historical energy data for '%s' (installation=%s, room=%s): "
        "%d days from %s to %s",
        device_name,
        installation_id,
        room_id,
        days_back,
        start_date.date(),
        end_date.date(),
    )

    all_energy_data = []
    current_date = end_date
    remaining_days = days_back
    chunk_count = 0
    failed_chunks = 0
    aggregation_reference_end_date = aggregation_reference_end_date or end_date

    while remaining_days > 0 and current_date > start_date:
        chunk_count += 1

        # Determine period and chunk size based on how far back we are
        days_back_from_reference = (aggregation_reference_end_date - current_date).days
        period, chunk_days = _determine_aggregation_period(
            days_back_from_reference, remaining_days
        )

        # Calculate chunk boundaries
        chunk_end = current_date
        chunk_start = max(
            current_date - dt_util.dt.timedelta(days=chunk_days), start_date
        )

        _LOGGER.debug(
            "Fetching chunk %d for '%s': period=%s, range=%s to %s (%d days)",
            chunk_count,
            device_name,
            period,
            chunk_start.date(),
            chunk_end.date(),
            chunk_days,
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
                    "Successfully fetched chunk %d for '%s': %d data points "
                    "(%s aggregation)",
                    chunk_count,
                    device_name,
                    len(energy_data),
                    period,
                )
            else:
                _LOGGER.debug(
                    "No data returned for chunk %d for '%s': period %s to %s",
                    chunk_count,
                    device_name,
                    chunk_start.date(),
                    chunk_end.date(),
                )
        except FenixTFTApiError as err:
            failed_chunks += 1
            _LOGGER.warning(
                "Failed to fetch chunk %d for '%s' (period=%s, range=%s to %s): %s",
                chunk_count,
                device_name,
                period,
                chunk_start.date(),
                chunk_end.date(),
                err,
            )

        # Move to next chunk
        current_date = chunk_start
        remaining_days -= chunk_days
        await asyncio.sleep(API_RATE_LIMIT_DELAY)

    _LOGGER.info(
        "Completed data fetch for '%s': %d total data points from %d chunks "
        "(%d successful, %d failed)",
        device_name,
        len(all_energy_data),
        chunk_count,
        chunk_count - failed_chunks,
        failed_chunks,
    )

    return all_energy_data


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

    async def async_import_historical_statistics(  # noqa: PLR0912, PLR0915
        call: ServiceCall,
    ) -> None:
        """Handle import_historical_statistics service call."""
        energy_entity_id = call.data[ATTR_ENERGY_ENTITY]
        days_back = call.data[ATTR_DAYS_BACK]
        import_all_history = call.data[ATTR_IMPORT_ALL_HISTORY]

        _LOGGER.info(
            "Historical import service called for entity '%s': %s",
            energy_entity_id,
            (
                "requesting all available history"
                if import_all_history
                else f"requesting {days_back} day(s) of data"
            ),
        )

        # Extract device context from entity
        config_entry, device_id, room_id, installation_id, device_data = (
            _get_device_context_from_entity(hass, energy_entity_id)
        )
        device_name = device_data.get("name", "Unknown Device")

        _LOGGER.debug(
            "Resolved device context for '%s': device_id=%s, room_id=%s, "
            "installation_id=%s",
            device_name,
            device_id,
            room_id,
            installation_id,
        )

        # For historical data, use external statistics to avoid interfering
        # with the main sensor entity
        clean_id = energy_entity_id.replace("sensor.", "")
        statistic_id = f"fenix_tft:{clean_id}_history"

        # Check if we have existing statistics in the external statistic
        first_stat_time = await get_first_statistic_time(hass, statistic_id)
        end_date = _calculate_import_end_date(first_stat_time)

        # Log import strategy
        if import_all_history:
            _LOGGER.info(
                "Import strategy for '%s': progressive backfill before %s until %s",
                device_name,
                end_date.strftime("%Y-%m-%d %H:%M:%S"),
                FULL_HISTORY_EARLIEST_DATE.strftime("%Y-%m-%d %H:%M:%S"),
            )
        elif first_stat_time:
            start_date, _, days_to_import = _calculate_import_date_range(
                days_back, first_stat_time
            )
            _LOGGER.info(
                "Import strategy for '%s': backfilling %d days before existing data "
                "(first statistic: %s, import range: %s to %s)",
                device_name,
                days_back,
                first_stat_time.strftime("%Y-%m-%d %H:%M:%S"),
                start_date.strftime("%Y-%m-%d %H:%M:%S"),
                end_date.strftime("%Y-%m-%d %H:%M:%S"),
            )
        else:
            start_date, _, days_to_import = _calculate_import_date_range(
                days_back, first_stat_time
            )
            _LOGGER.info(
                "Import strategy for '%s': no existing statistics found, "
                "importing %d days from present (import range: %s to %s)",
                device_name,
                days_back,
                start_date.strftime("%Y-%m-%d %H:%M:%S"),
                end_date.strftime("%Y-%m-%d %H:%M:%S"),
            )

        # Create start notification
        notification_id = f"fenix_import_{energy_entity_id.replace('.', '_')}"
        if import_all_history:
            import_msg = (
                f"Starting full historical data import for {device_name}. "
                "Older energy history will be imported in yearly batches until no "
                "more data is available."
            )
        else:
            import_msg = (
                f"Starting historical data import for {device_name}. "
                f"Importing {days_to_import} days of energy data"
            )
            if first_stat_time:
                import_msg += (
                    " (before existing data from "
                    f"{first_stat_time.strftime('%Y-%m-%d')})"
                )
        import_msg += ". This may take a while."

        async_create(
            hass,
            import_msg,
            title="Fenix TFT Historical Import",
            notification_id=notification_id,
        )

        # Get API and subscription ID
        api = config_entry.runtime_data["api"]
        subscription_id = api.subscription_id
        if not subscription_id:
            _LOGGER.error(
                "Cannot import historical data for '%s': subscription ID is missing",
                device_name,
            )
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="missing_subscription_id",
                message=(
                    "Subscription ID is missing; cannot import historical data. "
                    "Please re-authenticate or check your account permissions."
                ),
            )

        _LOGGER.debug(
            "Using subscription ID '%s' for historical data import",
            subscription_id,
        )

        try:
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

            imported_stat_count = 0
            imported_raw_points = 0
            imported_batches = 0
            imported_range_start: dt_util.dt.datetime | None = None
            imported_range_end: dt_util.dt.datetime | None = None

            def _track_imported_range(
                batch_start_time: dt_util.dt.datetime | None,
                batch_end_time: dt_util.dt.datetime | None,
            ) -> None:
                nonlocal imported_range_start, imported_range_end
                if batch_start_time and (
                    imported_range_start is None
                    or batch_start_time < imported_range_start
                ):
                    imported_range_start = batch_start_time
                if batch_end_time and (
                    imported_range_end is None or batch_end_time > imported_range_end
                ):
                    imported_range_end = batch_end_time

            if import_all_history:
                current_end = end_date
                has_future_stats = first_stat_time is not None

                while current_end > FULL_HISTORY_EARLIEST_DATE:
                    batch_start = max(
                        FULL_HISTORY_EARLIEST_DATE,
                        current_end
                        - dt_util.dt.timedelta(days=FULL_HISTORY_BATCH_DAYS),
                    )
                    batch_days = (current_end - batch_start).days

                    all_energy_data = await _fetch_historical_energy_data(
                        api,
                        installation_id,
                        room_id,
                        subscription_id,
                        batch_start,
                        current_end,
                        batch_days,
                        device_name,
                        aggregation_reference_end_date=end_date,
                    )

                    if all_energy_data:
                        imported_batches += 1
                        imported_raw_points += len(all_energy_data)
                        (
                            batch_stat_count,
                            _batch_sum,
                            batch_range_start,
                            batch_range_end,
                        ) = await _import_energy_statistics_batch(
                            hass,
                            energy_entity_id,
                            energy_metadata,
                            statistic_id,
                            all_energy_data,
                            current_end if has_future_stats else None,
                        )
                        imported_stat_count += batch_stat_count
                        _track_imported_range(batch_range_start, batch_range_end)
                        has_future_stats = True

                    current_end = batch_start
            else:
                start_date, end_date, days_to_import = _calculate_import_date_range(
                    days_back, first_stat_time
                )
                all_energy_data = await _fetch_historical_energy_data(
                    api,
                    installation_id,
                    room_id,
                    subscription_id,
                    start_date,
                    end_date,
                    days_back,
                    device_name,
                )

                if all_energy_data:
                    imported_batches = 1
                    imported_raw_points = len(all_energy_data)
                    (
                        imported_stat_count,
                        _batch_sum,
                        batch_range_start,
                        batch_range_end,
                    ) = await _import_energy_statistics_batch(
                        hass,
                        energy_entity_id,
                        energy_metadata,
                        statistic_id,
                        all_energy_data,
                        end_date if first_stat_time else None,
                    )
                    _track_imported_range(batch_range_start, batch_range_end)
                else:
                    _LOGGER.warning(
                        "No data fetched for '%s' in the requested date range "
                        "(%s to %s). "
                        "The device may not have been active during this period.",
                        device_name,
                        start_date.strftime("%Y-%m-%d"),
                        end_date.strftime("%Y-%m-%d"),
                    )

            # Success notification
            if imported_stat_count:
                range_msg = ""
                if imported_range_start and imported_range_end:
                    range_msg = (
                        f" Imported {imported_stat_count} statistic point(s) "
                        f"covering {imported_range_start.date()} to "
                        f"{imported_range_end.date()} from "
                        f"{imported_batches} batch(es)."
                    )
                success_msg = (
                    f"Successfully imported historical energy data for {device_name}."
                    f"{range_msg} Data is available as an external statistic "
                    f"({statistic_id}) and can be added to the Energy Dashboard."
                )
            else:
                success_msg = (
                    f"No additional historical energy data was available for "
                    f"{device_name}. The external statistic ({statistic_id}) "
                    "is up to date."
                )
            async_create(
                hass,
                success_msg,
                title="Fenix TFT Historical Import Complete",
                notification_id=notification_id,
            )

            _LOGGER.info(
                "Historical import completed successfully for '%s': %d raw point(s), "
                "%d statistic(s), %d batch(es)",
                device_name,
                imported_raw_points,
                imported_stat_count,
                imported_batches,
            )

        except (FenixTFTApiError, ServiceValidationError) as err:
            # Surface validation and API errors via notification before re-raising
            _LOGGER.exception(
                "Validation/API error during historical data import for '%s' "
                "(entity: %s)",
                device_name,
                energy_entity_id,
            )
            error_msg = f"Failed to import historical data for {device_name}: {err}"
            async_create(
                hass,
                error_msg,
                title="Fenix TFT Historical Import Failed",
                notification_id=notification_id,
            )
            raise
        except Exception as err:
            _LOGGER.exception(
                "Unexpected error during historical data import for '%s' (entity: %s)",
                device_name,
                energy_entity_id,
            )
            error_msg = f"Failed to import historical data for {device_name}: {err}"
            async_create(
                hass,
                error_msg,
                title="Fenix TFT Historical Import Failed",
                notification_id=notification_id,
            )
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


async def async_migrate_entry(_hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate a config entry to the current version."""
    _LOGGER.debug(
        "Migrating config entry from version %s.%s",
        config_entry.version,
        config_entry.minor_version,
    )

    if config_entry.version > 1:
        _LOGGER.error(
            "Cannot migrate config entry: unknown version %s", config_entry.version
        )
        return False

    # Version 1 is the current version — nothing to migrate yet.
    # Future migrations will be added here as additional elif branches.
    _LOGGER.debug("Config entry migration complete (already at current version)")
    return True


async def async_remove_config_entry_device(
    _hass: HomeAssistant,
    config_entry: FenixTFTConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """
    Allow removal of an individual thermostat device from this config entry.

    Returns True if the device can safely be removed (it is no longer present
    in the coordinator data, i.e., it was deleted from the Fenix account).
    Returns False if the device is still active, preventing accidental removal.
    """
    runtime_data = getattr(config_entry, "runtime_data", None)
    if not runtime_data:
        return True
    coordinator = (
        runtime_data.get("coordinator") if isinstance(runtime_data, dict) else None
    )
    if not coordinator or not coordinator.data:
        return True
    for dev in coordinator.data:
        if (DOMAIN, dev.get("id")) in device_entry.identifiers:
            # Device is still active in the account — block removal
            return False
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
