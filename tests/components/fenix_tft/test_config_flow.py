"""Tests for the Fenix TFT config flow."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from pyfenixcontrol import (
    FenixControlAuthError,
    FenixControlConnectionError,
    FenixControlResponseError,
)

from custom_components.fenix_tft.config_flow import (
    AuthenticationError,
    CannotConnectError,
    validate_input,
)
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


@pytest.fixture
def mock_session():
    """Return the session validate_input gets from Home Assistant."""
    return MagicMock()


@pytest.fixture
def mock_password_auth(mock_session):
    """Patch PasswordAuth used by validate_input."""
    session = mock_session
    with (
        patch(
            "custom_components.fenix_tft.config_flow.async_create_clientsession",
            return_value=session,
        ),
        patch("custom_components.fenix_tft.config_flow.PasswordAuth") as mock_cls,
    ):
        mock_cls.return_value.async_login = AsyncMock()
        yield mock_cls.return_value


async def test_validate_input_logs_in(hass, mock_password_auth, mock_session, caplog):
    """Test that validate_input performs a full login with the credentials."""
    result = await validate_input(
        hass, {CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: MOCK_PASSWORD}
    )

    assert result[CONF_USERNAME] == MOCK_USERNAME
    assert MOCK_USERNAME not in caplog.text
    mock_password_auth.async_login.assert_awaited_once()
    mock_session.detach.assert_called_once()
    mock_session.close.assert_not_called()


@pytest.mark.parametrize(
    "error_mapping",
    [
        (FenixControlAuthError("bad credentials"), AuthenticationError),
        (FenixControlConnectionError("offline"), CannotConnectError),
        (FenixControlResponseError("HTTP 500", 500), CannotConnectError),
    ],
)
async def test_validate_input_maps_library_errors(
    hass, mock_password_auth, mock_session, error_mapping, caplog
):
    """Test that library errors map to the config flow's error classes."""
    error, expected = error_mapping
    caplog.set_level(logging.DEBUG, logger="custom_components.fenix_tft.config_flow")
    mock_password_auth.async_login.side_effect = error

    with pytest.raises(expected):
        await validate_input(
            hass, {CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: "wrong"}
        )

    mock_session.detach.assert_called_once()
    # Expected failures are shown in the form and logged at debug level only
    assert not [r for r in caplog.records if r.levelno > logging.DEBUG]
    assert any(
        r.levelno == logging.DEBUG
        and r.name == "custom_components.fenix_tft.config_flow"
        and str(error) in r.getMessage()
        for r in caplog.records
    )
    assert MOCK_USERNAME not in caplog.text


async def test_user_step_cannot_connect(hass):
    """Test the user step shows cannot_connect when the cloud is unreachable."""
    with patch(
        "custom_components.fenix_tft.config_flow.validate_input",
        side_effect=CannotConnectError,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: MOCK_PASSWORD},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.parametrize(
    ("source", "step_id"),
    [
        (config_entries.SOURCE_REAUTH, "reauth_confirm"),
        (config_entries.SOURCE_RECONFIGURE, "reconfigure"),
    ],
)
@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (AuthenticationError, "invalid_auth"),
        (CannotConnectError, "cannot_connect"),
        (Exception("Unexpected"), "unknown"),
    ],
)
async def test_reauth_and_reconfigure_errors_then_recover(  # noqa: PLR0913, PLR0917
    hass, mock_config_entry, source, step_id, side_effect, error
):
    """Each validation error shows on the form; correct credentials then recover."""
    mock_config_entry.add_to_hass(hass)
    context = {"source": source, "entry_id": mock_config_entry.entry_id}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context=context, data=mock_config_entry.data
    )
    with patch(
        "custom_components.fenix_tft.config_flow.validate_input",
        side_effect=side_effect,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: "wrong"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == step_id
    assert result["errors"] == {"base": error}

    with patch(
        "custom_components.fenix_tft.config_flow.validate_input",
        return_value={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: "right"},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_USERNAME: MOCK_USERNAME, CONF_PASSWORD: "right"},
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] in {"reauth_successful", "reconfigure_successful"}
    assert mock_config_entry.data[CONF_PASSWORD] == "right"
