"""Helper functions for Fenix TFT integration (holiday parsing & state)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util
from pyfenixcontrol import parse_holiday_date

if TYPE_CHECKING:
    from datetime import datetime


def parse_holiday_end(end_str: str | None) -> datetime | None:
    """
    Parse holiday end date string into timezone-aware datetime.

    Returns None if date is missing, epoch placeholder, or cannot be parsed.
    Note: We only parse the end date (H2) as the start date (H1) is unreliable
    and gets updated dynamically by the Fenix API.
    """
    if (end := parse_holiday_date(end_str)) is None:
        return None
    return end.replace(tzinfo=dt_util.get_default_time_zone())
