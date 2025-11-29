"""Helper functions for Fenix TFT integration (holiday parsing & state)."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.util import dt as dt_util

from .const import (
    HOLIDAY_DATE_FORMAT,
    HOLIDAY_EPOCH_DATE,
    PRESET_MODE_HOLIDAYS,
)

_LOGGER = logging.getLogger(__name__)


def parse_holiday_end(end_str: str | None) -> datetime | None:
    """
    Parse holiday end date string into timezone-aware datetime.

    Returns None if date is missing, epoch placeholder, or cannot be parsed.
    Note: We only parse the end date (H2) as the start date (H1) is unreliable
    and gets updated dynamically by the Fenix API.
    """
    if not end_str or end_str == HOLIDAY_EPOCH_DATE:
        return None

    tz = dt_util.get_default_time_zone()
    try:
        return datetime.strptime(end_str, HOLIDAY_DATE_FORMAT).replace(tzinfo=tz)
    except (ValueError, TypeError) as err:
        _LOGGER.debug("Failed to parse holiday end date (%s): %s", end_str, err)
        return None


def parse_holiday_window(
    start_str: str | None, end_str: str | None
) -> tuple[datetime | None, datetime | None]:
    """
    Parse holiday start/end strings into timezone-aware datetimes.

    DEPRECATED: This function is kept for backward compatibility but should not be
    used for validation. The start date (H1) is unreliable as it gets updated
    dynamically by the Fenix API. Use parse_holiday_end() and check preset_mode instead.

    Returns (None, None) if dates are missing, epoch placeholders, or cannot be parsed.
    """
    if not start_str or not end_str or HOLIDAY_EPOCH_DATE in (start_str, end_str):
        return None, None

    tz = dt_util.get_default_time_zone()
    try:
        start_dt = datetime.strptime(start_str, HOLIDAY_DATE_FORMAT).replace(tzinfo=tz)
        end_dt = datetime.strptime(end_str, HOLIDAY_DATE_FORMAT).replace(tzinfo=tz)
    except (ValueError, TypeError) as err:
        _LOGGER.debug(
            "Failed to parse holiday window (%s, %s): %s", start_str, end_str, err
        )
        return None, None

    return start_dt, end_dt


def is_holiday_active(
    preset_mode: int,
    end_str: str | None,
    now: datetime | None = None,
) -> bool:
    """
    Determine if a holiday schedule is currently active.

    Uses preset_mode (Cm field) and end date (H2) for validation.
    The start date (H1) is not used as it's unreliable and updated
    dynamically by the API.

    Conditions:
    - preset_mode == PRESET_MODE_HOLIDAYS (Cm=1)
    - end date exists and parses successfully
    - current time <= end date (haven't passed the end yet)
    """
    if preset_mode != PRESET_MODE_HOLIDAYS:
        return False

    end_dt = parse_holiday_end(end_str)
    if not end_dt:
        return False

    current = now or dt_util.now()
    return current <= end_dt
