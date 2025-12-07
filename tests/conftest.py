"""Root conftest for Fenix TFT tests."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Import pytest plugins from pytest-homeassistant-custom-component
pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


@pytest.fixture(scope="session")
def custom_components_path():
    """Return path to custom components."""
    return Path(__file__).parent.parent / "custom_components"


@pytest.fixture(autouse=True)
def skip_recorder_setup():
    """Patch recorder component setup to avoid database initialization in tests."""

    # Mock async_setup for recorder to prevent it from trying to initialize
    async def mock_recorder_setup(hass, config):
        """Mock recorder setup that does nothing."""
        return True

    with patch(
        "homeassistant.components.recorder.async_setup",
        side_effect=mock_recorder_setup,
    ):
        yield


@pytest.fixture(autouse=True)
def mock_recorder_stats():
    """Mock recorder statistics functions used by fenix_tft."""
    with (
        patch(
            "homeassistant.components.recorder.statistics.async_add_external_statistics",
            new_callable=AsyncMock,
        ),
        patch(
            "homeassistant.components.recorder.statistics.get_last_statistics",
            return_value={},
        ),
    ):
        yield
