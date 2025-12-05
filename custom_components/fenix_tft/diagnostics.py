"""Diagnostics support for Fenix TFT."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import FenixTFTConfigEntry

# Keys to redact from diagnostics data for privacy
TO_REDACT = {
    "username",
    "password",
    "access_token",
    "refresh_token",
    "id",
    "Id_deviceId",
    "S1",
    "serialno",
    "serial_number",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,  # noqa: ARG001
    entry: FenixTFTConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data["coordinator"]
    api = entry.runtime_data["api"]

    # Gather diagnostic data
    diagnostics_data = {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "domain": entry.domain,
            "unique_id": entry.unique_id,
            "data": async_redact_data(entry.data, TO_REDACT),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": str(coordinator.last_exception)
            if coordinator.last_exception
            else None,
            "update_interval": str(coordinator.update_interval),
            "device_count": len(coordinator.data) if coordinator.data else 0,
        },
        "api": {
            "subscription_id": api.subscription_id,
            "has_access_token": bool(api.subscription_id),  # Proxy for token status
            "has_refresh_token": bool(api.subscription_id),
        },
        "devices": [],
    }

    # Add device information (redacted)
    if coordinator.data:
        for device in coordinator.data:
            device_info = {
                "name": device.get("name"),
                "type": device.get("type"),
                "software": device.get("software"),
                "installation": device.get("installation"),
                "preset_mode": device.get("preset_mode"),
                "hvac_action": device.get("hvac_action"),
                "current_temp": device.get("current_temp"),
                "target_temp": device.get("target_temp"),
                "floor_temp": device.get("floor_temp"),
                "holiday_mode": device.get("holiday_mode"),
                "has_room_id": device.get("room_id") is not None,
                "has_installation_id": device.get("installation_id") is not None,
                "has_energy_data": device.get("daily_energy_consumption") is not None,
            }
            diagnostics_data["devices"].append(device_info)

    return diagnostics_data
