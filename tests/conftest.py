"""
Root test configuration.

Lightweight recorder mock so tests don't need a real SQLite database.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.helpers import recorder as recorder_helper


@pytest.fixture
def mock_recorder_before_hass():
    """
    Override default no-op: patch recorder.async_setup to skip real DB setup.

    Calls async_initialize_recorder so that hass.data[DATA_RECORDER] is populated,
    satisfying dependencies inside Recorder.__init__, without spinning up a real
    SQLite database or background thread.
    """

    async def _lightweight_setup(hass, config):
        recorder_helper.async_initialize_recorder(hass)
        return True

    with patch(
        "homeassistant.components.recorder.async_setup",
        side_effect=_lightweight_setup,
    ):
        yield
