"""Statistics utilities for Fenix TFT integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def get_last_statistic_sum(hass: HomeAssistant, statistic_id: str) -> float:
    """
    Get the last cumulative sum from existing statistics.

    Args:
        hass: Home Assistant instance
        statistic_id: The statistic ID to query

    Returns:
        Last cumulative sum value, or 0.0 if no statistics exist

    """

    def _get_last_stat() -> float:
        try:
            last_stats = get_last_statistics(
                hass, 1, statistic_id, convert_units=True, units=set()
            )
            if last_stats.get(statistic_id):
                last_value = last_stats[statistic_id][0].get("sum")
                if last_value is not None:
                    return float(last_value)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not get last statistic for %s: %s", statistic_id, err)
        return 0.0

    result = await get_instance(hass).async_add_executor_job(_get_last_stat)
    if result > 0:
        _LOGGER.debug(
            "Found existing cumulative sum for %s: %s",
            statistic_id,
            result,
        )
    return result


async def get_first_statistic_time(
    hass: HomeAssistant, statistic_id: str
) -> datetime | None:
    """
    Get the timestamp of the first (oldest) recorded statistic.

    Uses an optimized binary search approach to avoid expensive full-history scans
    for long-lived installations. Instead of querying from 1970 to now, we start
    with a reasonable recent window (30 days) and progressively expand backwards
    until we find statistics or reach a practical limit.

    Args:
        hass: Home Assistant instance
        statistic_id: The statistic ID to query

    Returns:
        Datetime of the first statistic, or None if no statistics exist

    """

    def _get_first_stat() -> datetime | None:
        try:
            now = dt_util.now()

            # Binary search windows: start with 30 days, then 90, 180, 365, 730, 1825 (5 years)
            # This avoids scanning decades of empty data for new installations
            search_windows_days = [30, 90, 180, 365, 730, 1825]

            for days_back in search_windows_days:
                start_time = now - dt_util.dt.timedelta(days=days_back)

                stats = statistics_during_period(
                    hass,
                    start_time,
                    now,
                    {statistic_id},  # Must be a set, not a list
                    "hour",
                    None,
                    {"sum"},
                )

                if stats.get(statistic_id):
                    first_stat = stats[statistic_id][0]
                    if first_time := first_stat.get("start"):
                        # Convert Unix timestamp to datetime if needed
                        if isinstance(first_time, (int, float)):
                            return dt_util.utc_from_timestamp(first_time)
                        return first_time

            # If no statistics found in 5 years, they likely don't exist
            return None

        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not get first statistic for %s: %s", statistic_id, err)
        return None

    result = await get_instance(hass).async_add_executor_job(_get_first_stat)
    if result:
        _LOGGER.debug(
            "Found first statistic for %s at %s",
            statistic_id,
            result,
        )
    return result


def create_energy_statistic_metadata(
    entity_id: str, entity_name: str
) -> StatisticMetaData:
    """
    Create StatisticMetaData for energy consumption.

    This creates metadata for importing statistics directly to the sensor entity,
    not as external statistics. This allows the historical data to appear
    under the sensor's own entity ID (e.g., sensor.victory_port_x) rather than
    a separate external statistic ID.

    Args:
        entity_id: Entity ID for the energy sensor (e.g., sensor.victory_port_x)
        entity_name: Human-readable entity name

    Returns:
        StatisticMetaData configured for sensor energy statistics

    """
    return StatisticMetaData(
        has_mean=False,
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=entity_name,
        source="recorder",  # Use recorder as source for sensor statistics
        statistic_id=entity_id,  # Use entity ID directly for sensor statistics
        unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        unit_class="energy",
    )


def convert_energy_api_data_to_statistics(
    api_data: list[dict[str, Any]], starting_sum: float = 0.0
) -> list[StatisticData]:
    """
    Convert API energy data to StatisticData objects.

    Args:
        api_data: List of energy consumption metrics from API
        starting_sum: Starting cumulative sum value (from existing statistics)

    Returns:
        List of StatisticData objects with cumulative sum

    """
    statistics = []
    cumulative_sum = starting_sum

    # Sort data by timestamp to ensure chronological order
    sorted_data = sorted(
        api_data,
        key=lambda x: x.get("startDateOfMetric", ""),
    )

    for item in sorted_data:
        if not isinstance(item, dict):
            continue

        # Parse start date
        start_date_str = item.get("startDateOfMetric")
        if not start_date_str:
            _LOGGER.warning("Missing startDateOfMetric in energy data: %s", item)
            continue

        try:
            # Parse ISO format date string and ensure UTC timezone
            start_dt = dt_util.parse_datetime(start_date_str)
            if start_dt is None:
                _LOGGER.warning("Failed to parse date: %s", start_date_str)
                continue

            # Ensure UTC timezone
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=dt_util.UTC)
            else:
                start_dt = start_dt.astimezone(dt_util.UTC)

            # Get energy value (in Wh) for this period
            period_value = item.get("sum", 0)

            # Validate period_value is numeric
            if not isinstance(period_value, (int, float)):
                _LOGGER.warning(
                    "Non-numeric energy value in API data: %s", period_value
                )
                continue

            # Clamp negative values and log
            if period_value < 0:
                _LOGGER.warning(
                    "Received negative energy value %s from API; "
                    "clamping to 0.0 for statistics",
                    period_value,
                )
                period_value = 0.0

            cumulative_sum += period_value

            _LOGGER.debug(
                "Energy data point: time=%s, period=%s, cumulative=%s",
                start_dt,
                period_value,
                cumulative_sum,
            )

            statistics.append(
                StatisticData(
                    start=start_dt,
                    state=cumulative_sum,  # State also shows cumulative for energy
                    sum=cumulative_sum,  # Cumulative total
                )
            )
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Error processing energy data item %s: %s", item, err)
            continue

    return statistics
