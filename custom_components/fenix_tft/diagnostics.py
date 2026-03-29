"""Diagnostics support for Fenix TFT integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_PASSWORD, CONF_USERNAME

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import FenixTFTConfigEntry

TO_REDACT: set[str] = {
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_ACCESS_TOKEN,
    # Integration-specific sensitive keys
    "email",
    "token",
    "access_token",
    "refresh_token",
    "client_id",
    "client_secret",
    "account_id",
    "subscription_id",
}


async def async_get_config_entry_diagnostics(
    _hass: HomeAssistant,
    entry: FenixTFTConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a Fenix TFT config entry."""
    coordinator = entry.runtime_data["coordinator"]

    devices_info = [
        {
            "id": dev.get("id"),
            "name": dev.get("name"),
            "installation": dev.get("installation"),
            "installation_id": dev.get("installation_id"),
            "room_id": dev.get("room_id"),
            "preset_mode": dev.get("preset_mode"),
            "hvac_action": dev.get("hvac_action"),
            "target_temp": dev.get("target_temp"),
            "current_temp": dev.get("current_temp"),
            "floor_temp": dev.get("floor_temp"),
            "daily_energy": dev.get("daily_energy"),
            "active_holiday_mode": dev.get("active_holiday_mode"),
            "holiday_mode": dev.get("holiday_mode"),
            "holiday_end": dev.get("holiday_end"),
            "software": dev.get("software"),
            "type": dev.get("type"),
        }
        for dev in coordinator.data or []
    ]

    last_update_time = getattr(coordinator, "last_update_success_time", None)
    update_interval = getattr(coordinator, "update_interval", None)

    return {
        "entry": async_redact_data(entry.data, TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_update_time": last_update_time.isoformat()
            if last_update_time
            else None,
            "update_interval_seconds": update_interval.total_seconds()
            if update_interval
            else None,
            "device_count": len(coordinator.data) if coordinator.data else 0,
            "pending_optimistic_updates": coordinator.pending_optimistic_update_count,
        },
        "devices": devices_info,
    }
