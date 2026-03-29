"""Tests for the Fenix TFT config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType

from custom_components.fenix_tft.config_flow import AuthenticationError
from custom_components.fenix_tft.const import DOMAIN

from .conftest import MOCK_PASSWORD, MOCK_USERNAME


@pytest.fixture
def mock_validate_input_success():
    """Patch validate_input to succeed."""
    with patch(
        "custom_components.fenix_tft.config_flow.validate_input",
        return_value={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: MOCK_PASSWORD},
    ) as mock:
        yield mock


@pytest.fixture
def mock_validate_input_auth_error():
    """Patch validate_input to raise AuthenticationError."""
    with patch(
        "custom_components.fenix_tft.config_flow.validate_input",
        side_effect=AuthenticationError,
    ) as mock:
        yield mock


@pytest.fixture
def mock_validate_input_unknown_error():
    """Patch validate_input to raise an unexpected exception."""
    with patch(
        "custom_components.fenix_tft.config_flow.validate_input",
        side_effect=Exception("Unexpected"),
    ) as mock:
        yield mock


async def test_user_step_shows_form(hass):
    """Test the user step shows the login form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_user_step_success(hass, mock_validate_input_success):
    """Test a successful user config flow creates a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: MOCK_PASSWORD},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == MOCK_USERNAME
    assert result["data"][CONF_USERNAME] == MOCK_USERNAME


async def test_user_step_invalid_auth(hass, mock_validate_input_auth_error):
    """Test user flow shows error on invalid credentials."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: "wrong"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_step_unknown_error(hass, mock_validate_input_unknown_error):
    """Test user flow shows error on unexpected exception."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: MOCK_PASSWORD},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_user_step_duplicate_entry(
    hass, mock_config_entry, mock_validate_input_success
):
    """Test user flow aborts when the account is already configured."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: MOCK_PASSWORD},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_step_success(
    hass, mock_config_entry, mock_validate_input_success
):
    """Test reauthentication flow updates credentials and reloads."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=mock_config_entry.data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: "new_password"},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reauth_step_invalid_auth(
    hass, mock_config_entry, mock_validate_input_auth_error
):
    """Test reauthentication flow shows error on bad credentials."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=mock_config_entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: "wrong"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_step_success(
    hass, mock_config_entry, mock_validate_input_success
):
    """Test reconfigure flow updates credentials without removing entry."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": mock_config_entry.entry_id,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: "new_password_456"},
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_reconfigure_step_username_mismatch(hass, mock_config_entry):
    """Test reconfigure flow rejects a different username."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.fenix_tft.config_flow.validate_input",
        return_value={CONF_USERNAME: "other@example.com", CONF_PASSWORD: MOCK_PASSWORD},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": mock_config_entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                CONF_USERNAME: "other@example.com",
                CONF_PASSWORD: MOCK_PASSWORD,
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "username_exists"


async def test_validate_input_calls_api(hass):
    """Test that validate_input creates an API instance and calls login."""
    mock_api = AsyncMock()
    mock_api.login.return_value = True

    with patch(
        "custom_components.fenix_tft.config_flow.FenixTFTApi", return_value=mock_api
    ):
        from custom_components.fenix_tft.config_flow import validate_input

        result = await validate_input(
            hass, {CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: MOCK_PASSWORD}
        )

    assert result[CONF_USERNAME] == MOCK_USERNAME
    mock_api.login.assert_called_once()


async def test_validate_input_raises_on_failed_login(hass):
    """Test that validate_input raises AuthenticationError when login fails."""
    mock_api = AsyncMock()
    mock_api.login.return_value = False

    with (
        patch(
            "custom_components.fenix_tft.config_flow.FenixTFTApi", return_value=mock_api
        ),
        pytest.raises(AuthenticationError),
    ):
        from custom_components.fenix_tft.config_flow import validate_input

        await validate_input(
            hass, {CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: "wrong"}
        )
