"""Tests for writing recent hourly energy as external statistics."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.fenix_tft import statistics
from custom_components.fenix_tft.statistics import (
    async_import_recent_energy,
    recent_energy_statistic_id,
)

from .conftest import MOCK_ROOM_ID, energy_bucket

if TYPE_CHECKING:
    from collections.abc import Generator

NOW = datetime(2026, 11, 6, 0, 30, tzinfo=UTC)
STATISTIC_ID = recent_energy_statistic_id(MOCK_ROOM_ID)


def _utc(hour: int, day: int = 5) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=UTC)


@pytest.fixture
def recorder() -> Generator[MagicMock]:
    """Run recorder jobs inline and capture the written statistics."""
    instance = MagicMock()
    instance.async_add_executor_job = AsyncMock(
        side_effect=lambda func, *args: func(*args)
    )
    with (
        patch.object(statistics, "get_instance", return_value=instance),
        patch.object(statistics, "async_add_external_statistics") as add,
        patch.object(statistics, "statistics_during_period", return_value={}),
        patch.object(statistics, "get_last_statistics", return_value={}),
        patch.object(statistics.dt_util, "utcnow", return_value=NOW),
    ):
        instance.add = add
        yield instance


def _written(recorder: MagicMock) -> tuple[dict, list[tuple[datetime, float, float]]]:
    metadata, rows = recorder.add.call_args.args[1:]
    return metadata, [(row["start"], row["state"], row["sum"]) for row in rows]


async def test_buckets_booked_in_the_hour_they_cover(hass, recorder):
    """A bucket stamped at the end of an hour is booked at that hour's start."""
    written = await async_import_recent_energy(
        hass,
        MOCK_ROOM_ID,
        "Living Room",
        [energy_bucket(_utc(22), 1650.0), energy_bucket(_utc(21), 100.0)],
    )

    assert written == 2
    metadata, rows = _written(recorder)
    assert (
        metadata["statistic_id"]
        == STATISTIC_ID
        == ("fenix_tft:energy_aaaabbbb_cccc_dddd_eeee_111122223333")
    )
    assert metadata["name"] == "Living Room energy (hourly)"
    assert metadata["unit_of_measurement"] == "Wh"
    assert metadata["has_sum"] is True
    assert rows == [(_utc(20), 100.0, 100.0), (_utc(21), 1650.0, 1750.0)]


async def test_continues_sum_before_window(hass, recorder):
    """The running sum continues from the last row before the window."""
    with patch.object(
        statistics,
        "statistics_during_period",
        return_value={STATISTIC_ID: [{"sum": 9000.0}, {"sum": 9500.0}]},
    ) as during:
        await async_import_recent_energy(
            hass, MOCK_ROOM_ID, "Room", [energy_bucket(_utc(22), 100.0)]
        )

    _, rows = _written(recorder)
    assert rows == [(_utc(21), 100.0, 9600.0)]
    # Only rows before the first rewritten hour are looked at
    assert during.call_args.args[2] == _utc(21)


async def test_continues_older_sum_after_long_downtime(hass, recorder):
    """Without rows in the look-back, an older last row is continued."""
    old = _utc(0, day=1).timestamp()
    with patch.object(
        statistics,
        "get_last_statistics",
        return_value={STATISTIC_ID: [{"start": old, "sum": 4000.0}]},
    ):
        await async_import_recent_energy(
            hass, MOCK_ROOM_ID, "Room", [energy_bucket(_utc(22), 100.0)]
        )

    _, rows = _written(recorder)
    assert rows == [(_utc(21), 100.0, 4100.0)]


async def test_ignores_last_row_inside_window(hass, recorder):
    """A last row inside the rewritten window is not a base: start from 0."""
    inside = _utc(21).timestamp()
    with patch.object(
        statistics,
        "get_last_statistics",
        return_value={STATISTIC_ID: [{"start": inside, "sum": 4000.0}]},
    ):
        await async_import_recent_energy(
            hass, MOCK_ROOM_ID, "Room", [energy_bucket(_utc(22), 100.0)]
        )

    _, rows = _written(recorder)
    assert rows == [(_utc(21), 100.0, 100.0)]


async def test_skips_incomplete_and_undated_buckets(hass, recorder):
    """Hours not over yet, undated buckets and negative values are not written."""
    written = await async_import_recent_energy(
        hass,
        MOCK_ROOM_ID,
        "Room",
        [
            energy_bucket(_utc(0, day=6), 50.0),  # 23:00-24:00 UTC: complete
            energy_bucket(_utc(1, day=6), 30.0),  # 00:00-01:00 UTC: still running
            energy_bucket(_utc(23), -5.0),
            energy_bucket(None, 70.0),
        ],
    )

    assert written == 2
    _, rows = _written(recorder)
    assert rows == [(_utc(22), 0.0, 0.0), (_utc(23), 50.0, 50.0)]


async def test_nothing_to_write(hass, recorder):
    """Without complete hours nothing is written."""
    written = await async_import_recent_energy(
        hass, MOCK_ROOM_ID, "Room", [energy_bucket(_utc(1, day=6), 30.0)]
    )

    assert written == 0
    recorder.add.assert_not_called()


async def test_late_bucket_rewrites_following_sums(hass, recorder):
    """A bucket filled in late raises the sums of the hours after it."""
    await async_import_recent_energy(
        hass,
        MOCK_ROOM_ID,
        "Room",
        [energy_bucket(_utc(20), 100.0), energy_bucket(_utc(22), 300.0)],
    )
    await async_import_recent_energy(
        hass,
        MOCK_ROOM_ID,
        "Room",
        [
            energy_bucket(_utc(20), 100.0),
            energy_bucket(_utc(21), 200.0),
            energy_bucket(_utc(22), 300.0),
        ],
    )

    _, rows = _written(recorder)
    assert rows == [
        (_utc(19), 100.0, 100.0),
        (_utc(20), 200.0, 300.0),
        (_utc(21), 300.0, 600.0),
    ]
