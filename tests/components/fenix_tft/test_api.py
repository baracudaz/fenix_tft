"""Tests for the Fenix TFT API client's retry-on-5xx behavior."""

from __future__ import annotations

import time
from typing import Self
from unittest.mock import AsyncMock

import pytest

from custom_components.fenix_tft import api as api_module
from custom_components.fenix_tft.api import FenixTFTApi, FenixTFTApiError


class _FakeResponse:
    """Minimal async-context-manager stand-in for an aiohttp response."""

    def __init__(
        self, status: int, json_data: object = None, text_data: str = ""
    ) -> None:
        self.status = status
        self._json_data = json_data
        self._text_data = text_data

    async def json(self) -> object:
        return self._json_data

    async def text(self) -> str:
        return self._text_data

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None


class _FakeSession:
    """Fake aiohttp session that returns queued responses for each GET call."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    def get(self, _url: str, **_kwargs: object) -> _FakeResponse:
        self.call_count += 1
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid real delays during the retry backoff in tests."""
    monkeypatch.setattr(api_module.asyncio, "sleep", AsyncMock())


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


async def test_get_with_retry_raises_after_exhausting_retries() -> None:
    """A persistent 5xx is retried up to max_retries, then raises."""
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


async def test_get_with_retry_does_not_retry_client_errors() -> None:
    """A 4xx error is not retriable and fails immediately."""
    session = _FakeSession([_FakeResponse(404, text_data="not found")])
    api = _make_api(session)

    with pytest.raises(FenixTFTApiError):
        await api._get_with_retry("https://example/test", description="Test GET")

    assert session.call_count == 1


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
