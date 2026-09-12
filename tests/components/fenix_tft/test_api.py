"""Tests for the Fenix TFT API client's GET/PUT retry-on-5xx behavior."""

from __future__ import annotations

import json
import time
from typing import Self
from unittest.mock import AsyncMock

import pytest

from custom_components.fenix_tft import api as api_module
from custom_components.fenix_tft.api import (
    FenixTFTApi,
    FenixTFTApiError,
    FenixTFTAuthError,
)


class _FakeResponse:
    """Minimal async-context-manager stand-in for an aiohttp response."""

    def __init__(
        self, status: int, json_data: object = None, text_data: str | None = None
    ) -> None:
        self.status = status
        self._json_data = json_data
        # Mirror aiohttp: resp.json() is effectively json.loads(await resp.text()),
        # so default the body text to the serialized json_data unless overridden
        # (e.g. to simulate a malformed body).
        self._text_data = json.dumps(json_data) if text_data is None else text_data

    async def json(self) -> object:
        return self._json_data

    async def text(self) -> str:
        return self._text_data

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


class _FakeResponseBadJson(_FakeResponse):
    """A response whose .json() raises, simulating a malformed refresh body."""

    async def json(self) -> object:
        msg = "Expecting value"
        raise json.JSONDecodeError(msg, "", 0)


class _FakeSession:
    """Fake aiohttp session that returns queued responses for GET/PUT calls."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def get(self, _url: str, **_kwargs: object) -> _FakeResponse:
        self.call_count += 1
        return self._responses.pop(0)

    def put(self, _url: str, **_kwargs: object) -> _FakeResponse:
        self.call_count += 1
        return self._responses.pop(0)

    def post(self, _url: str, **_kwargs: object) -> _FakeResponse:
        self.call_count += 1
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def mock_sleep(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Avoid real delays during the retry backoff in tests, and expose the mock."""
    sleep_mock = AsyncMock()
    monkeypatch.setattr(api_module.asyncio, "sleep", sleep_mock)
    return sleep_mock


def _make_api(session: _FakeSession) -> FenixTFTApi:
    api = FenixTFTApi(session, "user@example.com", "password")
    api._access_token = "token"
    api._refresh_token = "refresh"
    api._token_expires = time.time() + 3600
    return api


async def test_get_with_retry_recovers_from_transient_502() -> None:
    """A transient 502 is retried and the eventual success is returned."""
    session = _FakeSession(
        [
            _FakeResponse(502, text_data="bad gateway"),
            _FakeResponse(200, json_data={"ok": True}),
        ]
    )
    api = _make_api(session)

    result = await api._get_with_retry("https://example/test", description="Test GET")

    assert result == {"ok": True}
    assert session.call_count == 2


async def test_get_with_retry_raises_after_exhausting_retries(
    mock_sleep: AsyncMock,
) -> None:
    """A persistent 5xx is retried up to max_retries with exponential backoff."""
    session = _FakeSession(
        [
            _FakeResponse(502, text_data="bad gateway"),
            _FakeResponse(502, text_data="bad gateway"),
            _FakeResponse(502, text_data="bad gateway"),
        ]
    )
    api = _make_api(session)

    with pytest.raises(FenixTFTApiError):
        await api._get_with_retry("https://example/test", description="Test GET")

    assert session.call_count == 3
    # Default max_retries=2 backs off 1s then 2s between attempts.
    mock_sleep.assert_any_await(1)
    mock_sleep.assert_any_await(2)
    assert mock_sleep.await_count == 2


async def test_get_with_retry_does_not_retry_client_errors() -> None:
    """A 4xx error is not retriable and fails immediately."""
    session = _FakeSession([_FakeResponse(404, text_data="not found")])
    api = _make_api(session)

    with pytest.raises(FenixTFTApiError):
        await api._get_with_retry("https://example/test", description="Test GET")

    assert session.call_count == 1


async def test_get_with_retry_raises_on_unexpected_status() -> None:
    """An unexpected non-4xx/5xx status code raises without retry."""
    session = _FakeSession([_FakeResponse(418, text_data="teapot")])
    api = _make_api(session)

    with pytest.raises(FenixTFTApiError):
        await api._get_with_retry("https://example/test", description="Test GET")

    assert session.call_count == 1


async def test_get_with_retry_raises_on_informational_status() -> None:
    """A 1xx status is not retried and raises, rather than being ignored."""
    session = _FakeSession([_FakeResponse(100, text_data="")])
    api = _make_api(session)

    with pytest.raises(FenixTFTApiError):
        await api._get_with_retry("https://example/test", description="Test GET")

    assert session.call_count == 1


async def test_get_with_retry_raises_on_redirect_status() -> None:
    """A 3xx status is not retried and raises, rather than being ignored."""
    session = _FakeSession([_FakeResponse(302, text_data="")])
    api = _make_api(session)

    with pytest.raises(FenixTFTApiError):
        await api._get_with_retry("https://example/test", description="Test GET")

    assert session.call_count == 1


async def test_get_with_retry_raises_fenix_error_on_invalid_json() -> None:
    """A malformed 200 body raises FenixTFTApiError, not a raw JSONDecodeError."""
    session = _FakeSession([_FakeResponse(200, text_data="not-json")])
    api = _make_api(session)

    with pytest.raises(FenixTFTApiError):
        await api._get_with_retry("https://example/test", description="Test GET")

    assert session.call_count == 1


@pytest.mark.parametrize(
    ("status", "expected"),
    [(100, "informational"), (204, "success-range"), (302, "redirect")],
)
def test_classify_unexpected_status(status: int, expected: str) -> None:
    """The classifier used for error-log wording covers 1xx/2xx-non-200/3xx."""
    assert api_module._classify_unexpected_status(status) == expected


async def test_get_device_properties_recovers_from_transient_502() -> None:
    """get_device_properties survives a single transient 502 from the API."""
    session = _FakeSession(
        [
            _FakeResponse(502, text_data="bad gateway"),
            _FakeResponse(200, json_data={"Cm": {"value": 6}}),
        ]
    )
    api = _make_api(session)

    result = await api.get_device_properties("AA11BB22CC00")

    assert result == {"Cm": {"value": 6}}
    assert session.call_count == 2


async def test_get_with_retry_returns_default_on_no_content_status() -> None:
    """A configured no-content status short-circuits without retrying or erroring."""
    session = _FakeSession([_FakeResponse(204)])
    api = _make_api(session)

    result = await api._get_with_retry(
        "https://example/test",
        description="Test GET",
        no_content_status=204,
        no_content_result=[],
    )

    assert result == []
    assert session.call_count == 1


async def test_get_room_energy_consumption_recovers_from_transient_502() -> None:
    """Room energy consumption retries transient 5xx like other GET endpoints."""
    session = _FakeSession(
        [
            _FakeResponse(502, text_data="bad gateway"),
            _FakeResponse(200, json_data=[{"processedDataWithAggregator": 100}]),
        ]
    )
    api = _make_api(session)

    result = await api.get_room_energy_consumption("AABB1122CCDD", "room-id", "sub-id")

    assert result == [{"processedDataWithAggregator": 100}]
    assert session.call_count == 2


async def test_get_room_energy_consumption_returns_empty_on_no_content() -> None:
    """A 204 from the energy endpoint means no data, not an error."""
    session = _FakeSession([_FakeResponse(204)])
    api = _make_api(session)

    result = await api.get_room_energy_consumption("AABB1122CCDD", "room-id", "sub-id")

    assert result == []
    assert session.call_count == 1


async def test_get_installations_recovers_from_transient_502() -> None:
    """get_installations survives a single transient 502 from the API."""
    session = _FakeSession(
        [
            _FakeResponse(502, text_data="bad gateway"),
            _FakeResponse(200, json_data=[{"id": "installation-1"}]),
        ]
    )
    api = _make_api(session)
    api._sub = "sub-id"  # skip the get_userinfo() lookup

    result = await api.get_installations()

    assert result == [{"id": "installation-1"}]
    assert session.call_count == 2


async def test_get_userinfo_recovers_from_transient_502() -> None:
    """get_userinfo survives a single transient 502 from the API."""
    session = _FakeSession(
        [
            _FakeResponse(502, text_data="bad gateway"),
            _FakeResponse(200, json_data={"sub": "user-123"}),
        ]
    )
    api = _make_api(session)

    result = await api.get_userinfo()

    assert result == {"sub": "user-123"}
    assert session.call_count == 2
    assert api._sub == "user-123"


async def test_get_userinfo_missing_sub_raises_error() -> None:
    """get_userinfo raises when the response body is missing 'sub'."""
    session = _FakeSession([_FakeResponse(200, json_data={})])
    api = _make_api(session)

    with pytest.raises(FenixTFTApiError):
        await api.get_userinfo()

    assert session.call_count == 1


async def test_put_with_retry_recovers_from_transient_502(
    mock_sleep: AsyncMock,
) -> None:
    """PUT shares the same backoff-on-5xx behavior as GET after de-duplication."""
    session = _FakeSession(
        [
            _FakeResponse(502, text_data="bad gateway"),
            _FakeResponse(200, text_data='{"ok": true}'),
        ]
    )
    api = _make_api(session)

    result = await api._put_with_retry(
        "https://example/test", {"key": "value"}, description="Test PUT"
    )

    assert result == {"ok": True}
    assert session.call_count == 2
    mock_sleep.assert_any_await(1)


async def test_put_with_retry_does_not_retry_client_errors() -> None:
    """A 4xx PUT response is not retriable and fails immediately."""
    session = _FakeSession([_FakeResponse(404, text_data="not found")])
    api = _make_api(session)

    with pytest.raises(FenixTFTApiError):
        await api._put_with_retry(
            "https://example/test", {"key": "value"}, description="Test PUT"
        )

    assert session.call_count == 1


async def test_put_with_retry_raises_on_invalid_json_success_body() -> None:
    """A 200 response with a non-JSON body is not retried but raises."""
    session = _FakeSession([_FakeResponse(200, text_data="not-json")])
    api = _make_api(session)

    with pytest.raises(FenixTFTApiError):
        await api._put_with_retry(
            "https://example/test", {"key": "value"}, description="Test PUT"
        )

    assert session.call_count == 1


async def test_get_with_retry_recovers_from_401_via_token_refresh() -> None:
    """A 401 triggers a token refresh (via the refresh token) and one retry."""
    session = _FakeSession(
        [
            _FakeResponse(401, text_data="unauthorized"),
            _FakeResponse(  # refresh token POST
                200, json_data={"access_token": "new-token", "expires_in": 3600}
            ),
            _FakeResponse(200, json_data={"ok": True}),
        ]
    )
    api = _make_api(session)

    result = await api._get_with_retry("https://example/test", description="Test GET")

    assert result == {"ok": True}
    assert api._access_token == "new-token"
    assert session.call_count == 3


async def test_get_with_retry_falls_back_to_login_after_refresh_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the refresh token itself is rejected, a full re-login is attempted."""
    session = _FakeSession(
        [
            _FakeResponse(401, text_data="unauthorized"),
            _FakeResponse(400, text_data="invalid_grant"),  # refresh token POST fails
            _FakeResponse(200, json_data={"ok": True}),
        ]
    )
    api = _make_api(session)

    async def fake_login() -> bool:
        api._access_token = "relogin-token"
        api._refresh_token = "relogin-refresh"
        return True

    monkeypatch.setattr(api, "login", fake_login)

    result = await api._get_with_retry("https://example/test", description="Test GET")

    assert result == {"ok": True}
    assert api._access_token == "relogin-token"


async def test_get_with_retry_falls_back_to_login_on_malformed_refresh_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A non-FenixTFTAuthError failure while refreshing still falls back to login.

    A malformed refresh response body raises json.JSONDecodeError rather than
    FenixTFTAuthError; that must not escape _reauthenticate_after_401() and
    skip the full re-login fallback.
    """
    session = _FakeSession(
        [
            _FakeResponse(401, text_data="unauthorized"),
            _FakeResponseBadJson(200),  # refresh token POST returns malformed body
            _FakeResponse(200, json_data={"ok": True}),
        ]
    )
    api = _make_api(session)

    async def fake_login() -> bool:
        api._access_token = "relogin-token"
        api._refresh_token = "relogin-refresh"
        return True

    monkeypatch.setattr(api, "login", fake_login)

    result = await api._get_with_retry("https://example/test", description="Test GET")

    assert result == {"ok": True}
    assert api._access_token == "relogin-token"


async def test_get_with_retry_raises_auth_error_when_reauth_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If both refresh and full re-login fail, FenixTFTAuthError is raised."""
    session = _FakeSession(
        [
            _FakeResponse(401, text_data="unauthorized"),
            _FakeResponse(400, text_data="invalid_grant"),  # refresh token POST fails
        ]
    )
    api = _make_api(session)
    monkeypatch.setattr(api, "login", AsyncMock(return_value=False))

    with pytest.raises(FenixTFTAuthError):
        await api._get_with_retry("https://example/test", description="Test GET")


async def test_get_with_retry_raises_auth_error_on_persistent_401() -> None:
    """
    A 401 surviving one reauth attempt raises FenixTFTAuthError.

    Not a generic FenixTFTApiError, so the coordinator triggers Home
    Assistant reauth instead of retrying forever.
    """
    session = _FakeSession(
        [
            _FakeResponse(401, text_data="unauthorized"),
            _FakeResponse(  # refresh token POST succeeds
                200, json_data={"access_token": "new-token", "expires_in": 3600}
            ),
            _FakeResponse(401, text_data="unauthorized"),  # still 401 after refresh
        ]
    )
    api = _make_api(session)

    with pytest.raises(FenixTFTAuthError):
        await api._get_with_retry("https://example/test", description="Test GET")

    assert session.call_count == 3


async def test_get_installations_refreshes_token_on_every_call() -> None:
    """
    get_installations() must call _ensure_token() even with self._sub cached.

    Otherwise a proactively-expiring token is never refreshed after the
    first successful poll (only get_userinfo() would have refreshed it,
    and it is skipped once _sub is known).
    """
    session = _FakeSession([_FakeResponse(200, json_data=[{"id": "installation-1"}])])
    api = _make_api(session)
    api._sub = "sub-id"

    ensure_token = AsyncMock(wraps=api._ensure_token)
    api._ensure_token = ensure_token

    result = await api.get_installations()

    assert result == [{"id": "installation-1"}]
    ensure_token.assert_awaited_once()


async def test_get_devices_propagates_auth_error_instead_of_returning_empty() -> None:
    """
    A FenixTFTAuthError from get_installations must reach the coordinator.

    It must not be swallowed by get_devices' broad FenixTFTApiError handling
    (which would otherwise silently report zero devices forever).
    """
    session = _FakeSession(
        [
            _FakeResponse(401, text_data="unauthorized"),
            _FakeResponse(400, text_data="invalid_grant"),
        ]
    )
    api = _make_api(session)
    api._sub = "sub-id"
    api.login = AsyncMock(return_value=False)

    with pytest.raises(FenixTFTAuthError):
        await api.get_devices()
