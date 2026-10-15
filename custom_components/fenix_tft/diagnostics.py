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

    data = coordinator.data
    devices_info = [
        {
            "id": dev.id,
            "name": dev.name,
            "installation": dev.installation_name,
            "installation_id": dev.installation_id,
            "room_id": dev.room_id,
            "preset_mode": dev.preset_mode,
            "hvac_action": dev.hvac_state,
            "target_temp": dev.target_temperature,
            "current_temp": dev.room_temperature,
            "floor_temp": dev.floor_temperature,
            "daily_energy": data.daily_energy.get(dev.id),
            "active_holiday_mode": dev.active_holiday_mode,
            "holiday_mode": dev.holiday_mode,
            "holiday_end": dev.holiday_end,
            "software": dev.software_version,
            "type": dev.model,
        }
        for dev in (data.devices.values() if data else ())
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
            "device_count": len(data.devices) if data else 0,
            "pending_optimistic_updates": coordinator.pending_optimistic_update_count,
        },
        "devices": devices_info,
    }
