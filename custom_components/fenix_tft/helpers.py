"""Helper functions for Fenix TFT integration (holiday parsing & state)."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.util import dt as dt_util

from .const import HOLIDAY_DATE_FORMAT, HOLIDAY_EPOCH_DATE, HOLIDAY_MODE_NONE

_LOGGER = logging.getLogger(__name__)


def parse_holiday_window(
    start_str: str | None, end_str: str | None
) -> tuple[datetime | None, datetime | None]:
    """
    Parse holiday start/end strings into timezone-aware datetimes.

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
    holiday_mode: int,
    start_str: str | None,
    end_str: str | None,
    now: datetime | None = None,
) -> bool:
    """
    Determine if a holiday schedule is currently active.

    Conditions:
    - holiday_mode != HOLIDAY_MODE_NONE
    - start/end parse successfully
    - current time is within [start, end]
    """
    if holiday_mode == HOLIDAY_MODE_NONE:
        return False

    start_dt, end_dt = parse_holiday_window(start_str, end_str)
    if not start_dt or not end_dt:
        return False

    current = now or dt_util.now()
    return start_dt <= current <= end_dt
