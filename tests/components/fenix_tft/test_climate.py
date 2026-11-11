"""Tests for the Fenix TFT climate entity."""

from __future__ import annotations

import dataclasses

import pytest
from homeassistant.components.climate import (
    ATTR_TARGET_TEMP_STEP,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pyfenixcontrol import FenixControlConnectionError

from custom_components.fenix_tft.const import (
    PRESET_MODE_BOOST,
    PRESET_MODE_DEFROST,
    PRESET_MODE_MANUAL,
    PRESET_MODE_OFF,
    PRESET_MODE_PROGRAM,
    TEMP_MAX,
    TEMP_MIN,
)

from .conftest import MOCK_DEVICE, MOCK_DEVICE_HOLIDAY, MOCK_DEVICE_ID


def _get_climate_entity_id(hass):
    """Get the climate entity ID for our mock device (installation + room name)."""
    # Entity ID is generated from device name: "{installation} {room}"
    # With MOCK_DEVICE: "Home Living Room" → "climate.home_living_room"
    states = hass.states.async_all("climate")
    assert states, "No climate entities found"
    return states[0].entity_id


async def test_climate_entity_created(hass, setup_integration):
    """Test that the climate entity is created after integration setup."""
    states = hass.states.async_all("climate")
    assert len(states) == 1


async def test_climate_initial_state(hass, setup_integration):
    """Test the climate entity's initial state matches mock device data."""
    entity_id = _get_climate_entity_id(hass)
    state = hass.states.get(entity_id)

    assert state is not None
    assert state.state == HVACMode.HEAT  # PRESET_MODE_MANUAL → HVAC HEAT
    assert float(state.attributes["current_temperature"]) == pytest.approx(19.2)
    assert float(state.attributes["temperature"]) == pytest.approx(22.5)
    # MANUAL mode does not map to a HA preset; preset_mode is None for HVAC modes
    assert state.attributes["preset_mode"] is None


@pytest.mark.parametrize(
    ("device_mode", "preset", "icon"),
    [
        (PRESET_MODE_PROGRAM, "program", "mdi:clock-outline"),
        (PRESET_MODE_DEFROST, "defrost", "mdi:snowflake"),
        (PRESET_MODE_BOOST, "boost", "mdi:fire"),
    ],
)
async def test_climate_reports_presets(  # noqa: PLR0913, PLR0917
    hass, mock_config_entry, mock_client, device_mode, preset, icon
):
    """Program, Defrost and Boost show as presets named like the modes."""
    mock_client.get_devices.return_value = [
        dataclasses.replace(MOCK_DEVICE, preset_mode=device_mode)
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_get_climate_entity_id(hass))
    assert state.state == HVACMode.AUTO
    assert state.attributes["preset_modes"] == ["program", "defrost", "boost"]
    assert state.attributes["preset_mode"] == preset
    assert state.attributes["icon"] == icon


@pytest.mark.parametrize(
    ("device_mode", "hvac_state", "action"),
    [
        (PRESET_MODE_MANUAL, 1, "heating"),
        (PRESET_MODE_MANUAL, 2, "idle"),  # TFT: target reached (#184)
        (PRESET_MODE_PROGRAM, 0, "idle"),  # WiFi Box: not heating
        (PRESET_MODE_OFF, 2, "off"),
        (PRESET_MODE_OFF, 0, "off"),
        (PRESET_MODE_OFF, 1, "off"),
        (PRESET_MODE_MANUAL, None, None),
    ],
)
async def test_climate_hvac_action(  # noqa: PLR0913, PLR0917
    hass, mock_config_entry, mock_client, device_mode, hvac_state, action
):
    """Not heating shows as idle; only the off mode shows as off."""
    mock_client.get_devices.return_value = [
        dataclasses.replace(MOCK_DEVICE, preset_mode=device_mode, hvac_state=hvac_state)
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_get_climate_entity_id(hass))
    assert state.attributes.get("hvac_action") == action


async def test_climate_hvac_action_unknown_during_holiday(
    hass, mock_config_entry, mock_client
):
    """During a holiday the heating state carries the holiday mode: no action."""
    mock_client.get_devices.return_value = [MOCK_DEVICE_HOLIDAY]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_get_climate_entity_id(hass))
    assert state.attributes.get("hvac_action") is None


# Sp of 21.0 shows that Defrost and Boost use their own setpoints (df, bo).
SETPOINT_DEVICE = dataclasses.replace(
    MOCK_DEVICE,
    active_target_temperature=21.0,
    defrost_temperature=7.0,
    boost_temperature=24.0,
    target_temperature_range=(5.0, 35.0),
    defrost_temperature_range=(1.94, 15.0),  # TFT reports raw 355-590 (35.5-59 °F)
    boost_temperature_range=(5.0, 35.0),
)


@pytest.mark.parametrize(
    ("device_mode", "setpoint", "min_temp", "max_temp"),
    [
        (PRESET_MODE_PROGRAM, 21.0, 5.0, 35.0),
        (PRESET_MODE_DEFROST, 7.0, 2.0, 15.0),
        (PRESET_MODE_BOOST, 24.0, 5.0, 35.0),
    ],
)
async def test_climate_target_outside_manual(  # noqa: PLR0913, PLR0917
    hass, mock_config_entry, mock_client, device_mode, setpoint, min_temp, max_temp
):
    """
    Program shows Sp; Defrost and Boost show df/bo with their own range (#186).

    The frost protection range (1.94-15 °C) is rounded inwards to 0.5 °C steps.
    """
    mock_client.get_devices.return_value = [
        dataclasses.replace(SETPOINT_DEVICE, preset_mode=device_mode)
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_get_climate_entity_id(hass))
    assert float(state.attributes["temperature"]) == pytest.approx(setpoint)
    assert float(state.attributes["min_temp"]) == pytest.approx(min_temp)
    assert float(state.attributes["max_temp"]) == pytest.approx(max_temp)
    assert (
        state.attributes["supported_features"] & ClimateEntityFeature.TARGET_TEMPERATURE
    )


async def test_manual_range_follows_device(hass, mock_config_entry, mock_client):
    """The WiFi Box accepts 10-30 °C for the manual target (#187)."""
    mock_client.get_devices.return_value = [
        dataclasses.replace(
            MOCK_DEVICE,
            target_temperature=22.5,
            target_temperature_range=(10.000001, 30.0),
        )
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _get_climate_entity_id(hass)

    state = hass.states.get(entity_id)
    assert float(state.attributes["min_temp"]) == 10.0
    assert float(state.attributes["max_temp"]) == 30.0
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, ATTR_TEMPERATURE: 8.0},
            blocking=True,
        )
    mock_client.set_setpoint.assert_not_called()


@pytest.mark.parametrize(
    ("device_mode", "preset", "temperature"),
    [
        (PRESET_MODE_DEFROST, "defrost", 8.0),
        (PRESET_MODE_BOOST, "boost", 23.0),
    ],
)
async def test_set_temperature_in_defrost_and_boost_keeps_mode(  # noqa: PLR0913, PLR0917
    hass, mock_config_entry, mock_client, device_mode, preset, temperature
):
    """Defrost and Boost get a new setpoint (df, bo) and stay in their mode."""
    mock_client.get_devices.return_value = [
        dataclasses.replace(SETPOINT_DEVICE, preset_mode=device_mode)
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": entity_id, ATTR_TEMPERATURE: temperature},
        blocking=True,
    )

    mock_client.set_setpoint.assert_called_once_with(
        MOCK_DEVICE_ID, device_mode, temperature
    )
    # The refresh still returns the old data; the new setpoint is kept
    state = hass.states.get(entity_id)
    assert state.attributes["preset_mode"] == preset
    assert float(state.attributes["temperature"]) == pytest.approx(temperature)


async def test_set_temperature_in_defrost_outside_range(
    hass, mock_config_entry, mock_client
):
    """Frost protection above 15 °C is rejected before reaching the cloud."""
    mock_client.get_devices.return_value = [
        dataclasses.replace(SETPOINT_DEVICE, preset_mode=PRESET_MODE_DEFROST)
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": _get_climate_entity_id(hass), ATTR_TEMPERATURE: 16.0},
            blocking=True,
        )
    mock_client.set_setpoint.assert_not_called()


async def test_defrost_without_setpoint_keeps_default_range(
    hass, mock_config_entry, mock_client
):
    """Without a reported df the default range stays and no target is shown."""
    mock_client.get_devices.return_value = [
        dataclasses.replace(
            MOCK_DEVICE, preset_mode=PRESET_MODE_DEFROST, defrost_temperature=None
        )
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_get_climate_entity_id(hass))
    assert state.attributes.get("temperature") is None
    assert float(state.attributes["min_temp"]) == TEMP_MIN
    assert float(state.attributes["max_temp"]) == TEMP_MAX


async def test_switch_to_away_shows_defrost_setpoint_at_once(
    hass, mock_config_entry, mock_client
):
    """After switching to Away the df setpoint shows before the cloud reports."""
    mock_client.get_devices.return_value = [
        dataclasses.replace(SETPOINT_DEVICE, preset_mode=PRESET_MODE_MANUAL)
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": entity_id, "preset_mode": "defrost"},
        blocking=True,
    )

    state = hass.states.get(entity_id)
    assert state.attributes["preset_mode"] == "defrost"
    assert float(state.attributes["temperature"]) == pytest.approx(7.0)


async def test_climate_no_target_when_off(hass, mock_config_entry, mock_client):
    """An off thermostat shows no target temperature."""
    mock_client.get_devices.return_value = [
        dataclasses.replace(MOCK_DEVICE, preset_mode=PRESET_MODE_OFF)
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_get_climate_entity_id(hass))
    assert state.attributes.get("temperature") is None


async def _setup_off(hass, mock_config_entry, mock_client):
    mock_client.get_devices.return_value = [
        dataclasses.replace(MOCK_DEVICE, preset_mode=PRESET_MODE_OFF)
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return _get_climate_entity_id(hass)


async def test_set_temperature_with_heat_mode_when_off(
    hass, mock_config_entry, mock_client
):
    """An off thermostat accepts a target together with the heat mode."""
    entity_id = await _setup_off(hass, mock_config_entry, mock_client)

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": entity_id, ATTR_TEMPERATURE: 21.5, "hvac_mode": HVACMode.HEAT},
        blocking=True,
    )

    mock_client.set_setpoint.assert_called_once_with(
        MOCK_DEVICE_ID, PRESET_MODE_MANUAL, 21.5
    )
    mock_client.set_preset_mode.assert_not_called()
    state = hass.states.get(entity_id)
    assert state.state == HVACMode.HEAT
    assert float(state.attributes["temperature"]) == pytest.approx(21.5)


async def test_set_temperature_alone_when_off_raises(
    hass, mock_config_entry, mock_client
):
    """A target alone doesn't turn on an off thermostat."""
    entity_id = await _setup_off(hass, mock_config_entry, mock_client)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, ATTR_TEMPERATURE: 21.5},
            blocking=True,
        )

    assert exc_info.value.translation_key == "no_target_mode"
    mock_client.set_setpoint.assert_not_called()


async def test_set_temperature_with_auto_mode(hass, setup_integration, mock_client):
    """A target with another HVAC mode sets the manual target, then that mode."""
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": entity_id, ATTR_TEMPERATURE: 21.5, "hvac_mode": HVACMode.AUTO},
        blocking=True,
    )

    mock_client.set_setpoint.assert_called_once_with(
        MOCK_DEVICE_ID, PRESET_MODE_MANUAL, 21.5
    )
    mock_client.set_preset_mode.assert_called_once_with(
        MOCK_DEVICE_ID, PRESET_MODE_PROGRAM
    )
    assert hass.states.get(entity_id).state == HVACMode.AUTO


async def test_set_temperature_with_unsupported_hvac_mode(
    hass, setup_integration, mock_client
):
    """An unsupported HVAC mode is rejected before any command is sent."""
    entity_id = _get_climate_entity_id(hass)

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {
                "entity_id": entity_id,
                ATTR_TEMPERATURE: 21.5,
                "hvac_mode": HVACMode.COOL,
            },
            blocking=True,
        )

    assert exc_info.value.translation_key == "unsupported_hvac_mode"
    mock_client.set_setpoint.assert_not_called()


async def test_set_temperature_in_program_switches_to_manual(
    hass, mock_config_entry, mock_client
):
    """Changing the target in program mode switches the thermostat to manual."""
    mock_client.get_devices.return_value = [
        dataclasses.replace(
            MOCK_DEVICE, preset_mode=PRESET_MODE_PROGRAM, active_target_temperature=20.0
        )
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": entity_id, ATTR_TEMPERATURE: 21.5},
        blocking=True,
    )

    mock_client.set_setpoint.assert_called_once_with(
        MOCK_DEVICE_ID, PRESET_MODE_MANUAL, 21.5
    )
    # The refresh still returns the old data; the new mode and target are kept
    state = hass.states.get(entity_id)
    assert state.state == HVACMode.HEAT
    assert float(state.attributes["temperature"]) == pytest.approx(21.5)


async def test_climate_min_max_temp(hass, setup_integration):
    """Test min/max temperature attributes match constants."""
    entity_id = _get_climate_entity_id(hass)
    state = hass.states.get(entity_id)

    assert float(state.attributes["min_temp"]) == TEMP_MIN
    assert float(state.attributes["max_temp"]) == TEMP_MAX
    assert float(state.attributes["target_temp_step"]) == 0.5


async def test_set_temperature_at_min_bound(hass, setup_integration, mock_client):
    """Allow setting temperature exactly at TEMP_MIN."""
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": entity_id, ATTR_TEMPERATURE: TEMP_MIN},
        blocking=True,
    )

    mock_client.set_setpoint.assert_called_once_with(
        MOCK_DEVICE_ID, PRESET_MODE_MANUAL, TEMP_MIN
    )


async def test_set_temperature_at_max_bound(hass, setup_integration, mock_client):
    """Allow setting temperature exactly at TEMP_MAX."""
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": entity_id, ATTR_TEMPERATURE: TEMP_MAX},
        blocking=True,
    )

    mock_client.set_setpoint.assert_called_once_with(
        MOCK_DEVICE_ID, PRESET_MODE_MANUAL, TEMP_MAX
    )


async def test_set_temperature_non_step_aligned_raises(
    hass, setup_integration, mock_client
):
    """Reject temperatures not aligned to TEMP_STEP (0.5°C)."""
    entity_id = _get_climate_entity_id(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, ATTR_TEMPERATURE: TEMP_MIN + 0.3},
            blocking=True,
        )

    mock_client.set_setpoint.assert_not_called()


async def test_set_temperature_fahrenheit_rounds_to_step(
    hass, setup_integration, mock_client
):
    """Round a target converted from °F to the 0.5 °C step instead of rejecting it."""
    entity_id = _get_climate_entity_id(hass)
    hass.config.units = US_CUSTOMARY_SYSTEM

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": entity_id, ATTR_TEMPERATURE: 72},
        blocking=True,
    )

    assert mock_client.set_setpoint.call_args.args[2] == 22.0


async def test_fahrenheit_target_step(hass, setup_integration, mock_client):
    """Step whole °F, so one step down reaches a new 0.5 °C target."""
    entity_id = _get_climate_entity_id(hass)
    assert hass.states.get(entity_id).attributes[ATTR_TARGET_TEMP_STEP] == 0.5
    hass.config.units = US_CUSTOMARY_SYSTEM

    # 20.5 °C shows as 69 °F; 0.5 °F down would round back to 20.5 °C
    for target_f, expected_c in ((69, 20.5), (68, 20.0)):
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, ATTR_TEMPERATURE: target_f},
            blocking=True,
        )
        assert mock_client.set_setpoint.call_args.args[2] == expected_c
    assert hass.states.get(entity_id).attributes[ATTR_TARGET_TEMP_STEP] == 1


async def test_set_temperature_calls_api(hass, setup_integration, mock_client):
    """Test that setting temperature calls the API."""
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": entity_id, ATTR_TEMPERATURE: 21.0},
        blocking=True,
    )

    mock_client.set_setpoint.assert_called_once_with(
        MOCK_DEVICE_ID, PRESET_MODE_MANUAL, 21.0
    )


async def test_set_temperature_below_min_raises(hass, setup_integration):
    """Test that setting temperature below TEMP_MIN raises ServiceValidationError."""
    entity_id = _get_climate_entity_id(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, ATTR_TEMPERATURE: TEMP_MIN - 1},
            blocking=True,
        )


async def test_set_temperature_above_max_raises(hass, setup_integration):
    """Test that setting temperature above TEMP_MAX raises ServiceValidationError."""
    entity_id = _get_climate_entity_id(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, ATTR_TEMPERATURE: TEMP_MAX + 1},
            blocking=True,
        )


async def test_set_temperature_holiday_locked(hass, mock_config_entry, mock_client):
    """Test that setting temperature is blocked when holiday mode is active."""
    mock_client.get_devices.return_value = [MOCK_DEVICE_HOLIDAY]
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = _get_climate_entity_id(hass)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, ATTR_TEMPERATURE: 21.0},
            blocking=True,
        )

    mock_client.set_setpoint.assert_not_called()


async def test_set_hvac_mode_off(hass, setup_integration, mock_client):
    """Test HVAC mode OFF calls set_device_preset_mode with PRESET_MODE_OFF."""
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": entity_id, "hvac_mode": HVACMode.OFF},
        blocking=True,
    )

    mock_client.set_preset_mode.assert_called_once_with(MOCK_DEVICE_ID, PRESET_MODE_OFF)


async def test_set_hvac_mode_heat(hass, setup_integration, mock_client):
    """Test HVAC mode HEAT calls set_device_preset_mode with PRESET_MODE_MANUAL."""
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": entity_id, "hvac_mode": HVACMode.HEAT},
        blocking=True,
    )

    mock_client.set_preset_mode.assert_called_once_with(
        MOCK_DEVICE_ID, PRESET_MODE_MANUAL
    )


async def test_set_preset_mode(hass, setup_integration, mock_client):
    """Test that setting a preset mode calls the API with the correct int code."""
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": entity_id, "preset_mode": "program"},
        blocking=True,
    )

    mock_client.set_preset_mode.assert_called_once_with(
        MOCK_DEVICE_ID, PRESET_MODE_PROGRAM
    )


@pytest.mark.parametrize(
    ("preset_mode", "expected_preset_value"),
    [
        ("home", PRESET_MODE_PROGRAM),
        ("program", PRESET_MODE_PROGRAM),
        ("away", PRESET_MODE_DEFROST),
        ("defrost", PRESET_MODE_DEFROST),
        ("eco", PRESET_MODE_DEFROST),
        ("boost", PRESET_MODE_BOOST),
        ("comfort", PRESET_MODE_BOOST),
    ],
)
async def test_set_preset_mode_legacy_and_new_names(
    hass,
    setup_integration,
    mock_client,
    preset_mode,
    expected_preset_value,
):
    """Test legacy and new preset names map to the expected device value."""
    entity_id = _get_climate_entity_id(hass)

    await hass.services.async_call(
        "climate",
        "set_preset_mode",
        {"entity_id": entity_id, "preset_mode": preset_mode},
        blocking=True,
    )

    mock_client.set_preset_mode.assert_called_once_with(
        MOCK_DEVICE_ID, expected_preset_value
    )


async def test_set_preset_mode_holiday_locked(hass, mock_config_entry, mock_client):
    """Test that changing preset mode is blocked when holiday mode is active."""
    mock_client.get_devices.return_value = [MOCK_DEVICE_HOLIDAY]
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_id = _get_climate_entity_id(hass)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "climate",
            "set_preset_mode",
            {"entity_id": entity_id, "preset_mode": "manual"},
            blocking=True,
        )

    mock_client.set_preset_mode.assert_not_called()


@pytest.mark.parametrize(
    ("service", "data", "client_method", "translation_key"),
    [
        (
            "set_temperature",
            {ATTR_TEMPERATURE: 21.0},
            "set_setpoint",
            "api_error_set_temperature",
        ),
        (
            "set_hvac_mode",
            {"hvac_mode": HVACMode.OFF},
            "set_preset_mode",
            "api_error_set_hvac_mode",
        ),
        (
            "set_preset_mode",
            {"preset_mode": "defrost"},
            "set_preset_mode",
            "api_error_set_preset_mode",
        ),
    ],
)
async def test_climate_command_error_raises_home_assistant_error(  # noqa: PLR0913, PLR0917
    hass, setup_integration, mock_client, service, data, client_method, translation_key
):
    """A failed cloud request surfaces as a translated HomeAssistantError."""
    getattr(mock_client, client_method).side_effect = FenixControlConnectionError(
        "offline"
    )

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            "climate",
            service,
            {"entity_id": _get_climate_entity_id(hass), **data},
            blocking=True,
        )

    assert exc_info.value.translation_key == translation_key
    assert isinstance(exc_info.value.__cause__, FenixControlConnectionError)


async def test_range_without_step_falls_back_to_default(
    hass, mock_config_entry, mock_client
):
    """A device range without a 0.5 °C step inside it uses the default range."""
    mock_client.get_devices.return_value = [
        dataclasses.replace(MOCK_DEVICE, target_temperature_range=(10.1, 10.4))
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(_get_climate_entity_id(hass))
    assert float(state.attributes["min_temp"]) == TEMP_MIN
    assert float(state.attributes["max_temp"]) == TEMP_MAX
