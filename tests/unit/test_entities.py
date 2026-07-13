from __future__ import annotations

import importlib
import sys
import time

# pyright: basic, reportUnusedFunction=false
from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.media_player import MediaPlayerState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

_ = sys.modules.setdefault("turbojpeg", MagicMock(TurboJPEG=MagicMock()))

_MODELS = importlib.import_module("custom_components.nanit.aionanit.models")
Baby = _MODELS.Baby
BreathingState = _MODELS.BreathingState
CameraState = _MODELS.CameraState
CloudEvent = _MODELS.CloudEvent
ConnectionInfo = _MODELS.ConnectionInfo
ConnectionState = _MODELS.ConnectionState
ControlState = _MODELS.ControlState
NightLightState = _MODELS.NightLightState
SensorState = _MODELS.SensorState
SettingsState = _MODELS.SettingsState


@dataclass(frozen=True)
class _PlaybackStateFallback:
    playing: bool = False
    current_track: str | None = None
    available_tracks: tuple[str, ...] = ()


PlaybackState = getattr(_MODELS, "PlaybackState", _PlaybackStateFallback)

from custom_components.nanit.binary_sensor import (
    BINARY_SENSORS,
    CLOUD_BINARY_SENSORS,
    NanitBinarySensor,
    NanitBreathingAlertBinarySensor,
    NanitBreathingTrackingBinarySensor,
    NanitCloudBinarySensor,
)
from custom_components.nanit.button import NanitStartBreathingButton
from custom_components.nanit.camera import NanitCameraEntity
from custom_components.nanit.const import CLOUD_EVENT_WINDOW
from custom_components.nanit.coordinator import (
    _AVAILABILITY_GRACE_SECONDS,
    NanitPushCoordinator,
)
from custom_components.nanit.media_player import NanitMediaPlayer
from custom_components.nanit.select import NanitSoundTimerSelect
from custom_components.nanit.sensor import SENSORS, NanitBreathingRateSensor, NanitSensor
from custom_components.nanit.switch import SWITCHES, NanitSwitch

from .conftest import MOCK_BABY_1

pytestmark = [
    pytest.mark.filterwarnings("ignore::pytest.PytestRemovedIn9Warning"),
]


async def _resolve_hass(hass: Any) -> HomeAssistant:
    if hasattr(hass, "__anext__"):
        return await hass.__anext__()
    return cast(HomeAssistant, hass)


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(enable_custom_integrations) -> Iterator[None]:
    _ = enable_custom_integrations
    yield


def _camera_state(
    *,
    temperature: float | None = 22.5,
    humidity: float | None = 50.0,
    light: int | None = 150,
    volume: int | None = 50,
    sleep_mode: bool | None = False,
    night_vision: bool | None = True,
    night_light: NightLightState | None = NightLightState.OFF,
    night_light_brightness: int | None = None,
    night_light_timeout: int | None = None,
    playback: PlaybackState | None = None,
    connection_state: ConnectionState = ConnectionState.CONNECTED,
    last_seen: Any = None,
) -> CameraState:
    kwargs: dict[str, Any] = {
        "sensors": SensorState(
            temperature=temperature,
            humidity=humidity,
            light=light,
        ),
        "settings": SettingsState(
            volume=volume,
            sleep_mode=sleep_mode,
            night_vision=night_vision,
            night_light_brightness=night_light_brightness,
        ),
        "control": ControlState(night_light=night_light, night_light_timeout=night_light_timeout),
        "connection": ConnectionInfo(state=connection_state, last_seen=last_seen),
    }
    if "playback" in getattr(CameraState, "__dataclass_fields__", {}):
        kwargs["playback"] = playback or PlaybackState()
        return CameraState(**kwargs)

    state = CameraState(**kwargs)
    object.__setattr__(state, "playback", playback or PlaybackState())
    return state


def _push_coordinator(
    state: CameraState | None,
    *,
    connected: bool = True,
    last_update_success: bool = True,
) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = state
    coordinator.camera = MagicMock(uid="cam_1", baby_uid="baby_1")
    coordinator.baby = Baby(uid="baby_1", name="Nursery", camera_uid="cam_1")
    coordinator.last_update_success = last_update_success
    coordinator.connected = connected
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


def _media_cam_data(
    coordinator: MagicMock,
    camera: MagicMock,
    *,
    sound_timer_seconds: int | None = None,
) -> MagicMock:
    """Build a minimal CameraData stand-in for NanitMediaPlayer."""
    cam_data = MagicMock()
    cam_data.push_coordinator = coordinator
    cam_data.camera = camera
    cam_data.sound_timer_seconds = sound_timer_seconds
    return cam_data


def _cloud_coordinator(events: list[CloudEvent] | None) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = events
    coordinator.baby = Baby(uid="baby_1", name="Nursery", camera_uid="cam_1")
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


def _sensor_description(key: str):
    return next(description for description in SENSORS if description.key == key)


def _binary_description(key: str):
    return next(description for description in BINARY_SENSORS if description.key == key)


def _cloud_binary_description(key: str):
    return next(description for description in CLOUD_BINARY_SENSORS if description.key == key)


def _switch_description(key: str):
    return next(description for description in SWITCHES if description.key == key)


def _disable_state_writes(entity: Any) -> None:
    entity.async_write_ha_state = MagicMock()


@pytest.mark.parametrize(
    ("sensor_key", "expected"),
    [
        ("temperature", 22.5),
        ("humidity", 50.0),
        ("light", 150),
    ],
)
def test_sensor_value_extraction(sensor_key: str, expected: float | int) -> None:
    coordinator = _push_coordinator(_camera_state())
    entity = NanitSensor(coordinator, _sensor_description(sensor_key))

    assert entity.native_value == expected


def test_sensor_returns_none_when_no_data() -> None:
    coordinator = _push_coordinator(None)
    entity = NanitSensor(coordinator, _sensor_description("temperature"))

    assert entity.native_value is None


def test_binary_sensor_connectivity_on_when_connected() -> None:
    coordinator = _push_coordinator(_camera_state(connection_state=ConnectionState.CONNECTED))
    entity = NanitBinarySensor(coordinator, _binary_description("connectivity"))

    assert entity.is_on is True


def test_binary_sensor_connectivity_off_when_disconnected() -> None:
    coordinator = _push_coordinator(
        _camera_state(connection_state=ConnectionState.DISCONNECTED), connected=False
    )
    entity = NanitBinarySensor(coordinator, _binary_description("connectivity"))

    assert entity.is_on is False


def test_binary_sensor_connectivity_is_always_available_when_disconnected() -> None:
    coordinator = _push_coordinator(_camera_state(), connected=False, last_update_success=True)
    entity = NanitBinarySensor(coordinator, _binary_description("connectivity"))

    assert entity.available is True


def test_binary_sensor_connectivity_not_available_without_successful_update() -> None:
    coordinator = _push_coordinator(_camera_state(), connected=True, last_update_success=False)
    entity = NanitBinarySensor(coordinator, _binary_description("connectivity"))

    assert entity.available is False


def _breathing_state(
    *,
    breaths_per_minute: int | None = 43,
    is_alert: bool = False,
    is_measuring: bool = True,
    age_seconds: float = 0.0,
) -> CameraState:
    return replace(
        _camera_state(),
        breathing=BreathingState(
            breaths_per_minute=breaths_per_minute,
            is_alert=is_alert,
            is_measuring=is_measuring,
            received_at=time.time() - age_seconds,
        ),
    )


def test_breathing_rate_value_and_availability_when_fresh() -> None:
    coordinator = _push_coordinator(_breathing_state(breaths_per_minute=43))
    entity = NanitBreathingRateSensor(coordinator)

    assert entity.native_value == 43
    assert entity.available is True


def test_breathing_rate_unavailable_when_stale() -> None:
    coordinator = _push_coordinator(_breathing_state(age_seconds=120))
    entity = NanitBreathingRateSensor(coordinator)

    assert entity.available is False


def test_breathing_rate_unavailable_without_data() -> None:
    coordinator = _push_coordinator(None)
    entity = NanitBreathingRateSensor(coordinator)

    assert entity.native_value is None
    assert entity.available is False


def test_breathing_alert_reflects_flag_and_freshness() -> None:
    on = NanitBreathingAlertBinarySensor(_push_coordinator(_breathing_state(is_alert=True)))
    off = NanitBreathingAlertBinarySensor(_push_coordinator(_breathing_state(is_alert=False)))
    stale = NanitBreathingAlertBinarySensor(
        _push_coordinator(_breathing_state(is_alert=True, age_seconds=120))
    )

    assert on.is_on is True
    assert on.available is True
    assert off.is_on is False
    assert stale.available is False


def test_breathing_tracking_binary_sensor_on_iff_fresh_and_measuring() -> None:
    """binary_sensor.breathing_tracking is ON iff a fresh session is measuring."""
    on = NanitBreathingTrackingBinarySensor(_push_coordinator(_breathing_state(is_measuring=True)))
    stale = NanitBreathingTrackingBinarySensor(
        _push_coordinator(_breathing_state(is_measuring=True, age_seconds=999))
    )

    assert on.is_on is True
    assert stale.available is True
    assert stale.is_on is False


def test_cloud_binary_motion_on_when_event_within_window() -> None:
    now = 10_000.0
    coordinator = _cloud_coordinator(
        [
            CloudEvent(
                event_type="MOTION",
                timestamp=now - (CLOUD_EVENT_WINDOW - 1),
                baby_uid="baby_1",
            )
        ]
    )
    entity = NanitCloudBinarySensor(coordinator, _cloud_binary_description("cloud_motion"))

    with patch("custom_components.nanit.binary_sensor.time_mod.time", return_value=now):
        assert entity.is_on is True


def test_cloud_binary_motion_matches_event_type_case_insensitively() -> None:
    now = 10_000.0
    coordinator = _cloud_coordinator(
        [
            CloudEvent(
                event_type="motion",
                timestamp=now - 1,
                baby_uid="baby_1",
            )
        ]
    )
    entity = NanitCloudBinarySensor(coordinator, _cloud_binary_description("cloud_motion"))

    with patch("custom_components.nanit.binary_sensor.time_mod.time", return_value=now):
        assert entity.is_on is True


def test_cloud_binary_sound_off_when_event_outside_window() -> None:
    now = 10_000.0
    coordinator = _cloud_coordinator(
        [
            CloudEvent(
                event_type="SOUND",
                timestamp=now - (CLOUD_EVENT_WINDOW + 1),
                baby_uid="baby_1",
            )
        ]
    )
    entity = NanitCloudBinarySensor(coordinator, _cloud_binary_description("cloud_sound"))

    with patch("custom_components.nanit.binary_sensor.time_mod.time", return_value=now):
        assert entity.is_on is False


def test_cloud_binary_sensor_off_when_no_events() -> None:
    coordinator = _cloud_coordinator([])
    entity = NanitCloudBinarySensor(coordinator, _cloud_binary_description("cloud_motion"))

    assert entity.is_on is False


async def test_switch_camera_power_turn_off_calls_sleep_mode() -> None:
    coordinator = _push_coordinator(_camera_state(sleep_mode=False))
    camera = MagicMock(uid="cam_1")
    camera.async_set_control = AsyncMock()
    camera.async_set_settings = AsyncMock()
    entity = NanitSwitch(coordinator, camera, _switch_description("camera_power"))
    _disable_state_writes(entity)

    with patch("custom_components.nanit.switch.time.monotonic", return_value=100.0):
        await entity.async_turn_off()

    camera.async_set_settings.assert_awaited_once_with(sleep_mode=True)
    assert entity.is_on is False


def test_media_player_state_playing_when_playback_playing_true() -> None:
    coordinator = _push_coordinator(
        _camera_state(playback=PlaybackState(playing=True, current_track="White Noise.wav"))
    )
    camera = MagicMock(uid="cam_1")
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))

    assert entity.state is MediaPlayerState.PLAYING


def test_media_player_state_none_when_no_data() -> None:
    coordinator = _push_coordinator(None)
    camera = MagicMock(uid="cam_1")
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))

    assert entity.state is None


def test_media_player_state_idle_when_playback_playing_false() -> None:
    coordinator = _push_coordinator(
        _camera_state(playback=PlaybackState(playing=False, current_track=None))
    )
    camera = MagicMock(uid="cam_1")
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))

    assert entity.state is MediaPlayerState.IDLE


def test_media_player_source_returns_current_track() -> None:
    coordinator = _push_coordinator(
        _camera_state(playback=PlaybackState(playing=True, current_track="Waves.wav"))
    )
    camera = MagicMock(uid="cam_1")
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))

    assert entity.source == "Waves.wav"


def test_media_player_source_none_when_no_data() -> None:
    coordinator = _push_coordinator(None)
    camera = MagicMock(uid="cam_1")
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))

    assert entity.source is None


def test_media_player_source_list_returns_available_tracks() -> None:
    coordinator = _push_coordinator(
        _camera_state(
            playback=PlaybackState(
                playing=True,
                current_track="White Noise.wav",
                available_tracks=("White Noise.wav", "Birds.wav", "Waves.wav"),
            )
        )
    )
    camera = MagicMock(uid="cam_1")
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))

    assert entity.source_list == ["White Noise.wav", "Birds.wav", "Waves.wav"]


def test_media_player_source_list_none_when_no_data() -> None:
    coordinator = _push_coordinator(None)
    camera = MagicMock(uid="cam_1")
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))

    assert entity.source_list is None


def test_media_player_volume_level_returns_settings_volume_scaled() -> None:
    coordinator = _push_coordinator(_camera_state(volume=75))
    camera = MagicMock(uid="cam_1")
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))

    assert entity.volume_level == 0.75


def test_media_player_volume_level_none_when_no_data() -> None:
    coordinator = _push_coordinator(None)
    camera = MagicMock(uid="cam_1")
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))

    assert entity.volume_level is None


def test_media_player_volume_level_none_when_volume_is_none() -> None:
    coordinator = _push_coordinator(_camera_state(volume=None))
    camera = MagicMock(uid="cam_1")
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))

    assert entity.volume_level is None


async def test_media_player_play_calls_camera_start_playback() -> None:
    coordinator = _push_coordinator(_camera_state())
    camera = MagicMock(uid="cam_1")
    camera.async_start_playback = AsyncMock()
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))
    _disable_state_writes(entity)

    await entity.async_media_play()

    camera.async_start_playback.assert_awaited_once_with(duration=None)


async def test_media_player_play_passes_sound_timer_duration() -> None:
    coordinator = _push_coordinator(_camera_state())
    camera = MagicMock(uid="cam_1")
    camera.async_start_playback = AsyncMock()
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera, sound_timer_seconds=3600))
    _disable_state_writes(entity)

    await entity.async_media_play()

    camera.async_start_playback.assert_awaited_once_with(duration=3600)


async def test_media_player_stop_calls_camera_stop_playback() -> None:
    coordinator = _push_coordinator(_camera_state())
    camera = MagicMock(uid="cam_1")
    camera.async_stop_playback = AsyncMock()
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))
    _disable_state_writes(entity)

    await entity.async_media_stop()

    camera.async_stop_playback.assert_awaited_once_with()


async def test_media_player_select_source_calls_start_playback_with_track() -> None:
    coordinator = _push_coordinator(_camera_state())
    camera = MagicMock(uid="cam_1")
    camera.async_start_playback = AsyncMock()
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))
    _disable_state_writes(entity)

    await entity.async_select_source("Birds.wav")

    camera.async_start_playback.assert_awaited_once_with(track="Birds.wav", duration=None)


async def test_media_player_select_source_passes_sound_timer_duration() -> None:
    coordinator = _push_coordinator(_camera_state())
    camera = MagicMock(uid="cam_1")
    camera.async_start_playback = AsyncMock()
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera, sound_timer_seconds=900))
    _disable_state_writes(entity)

    await entity.async_select_source("Birds.wav")

    camera.async_start_playback.assert_awaited_once_with(track="Birds.wav", duration=900)


def test_sound_timer_select_defaults_to_continuous() -> None:
    coordinator = _push_coordinator(_camera_state())
    cam_data = _media_cam_data(coordinator, MagicMock(uid="cam_1"))
    entity = NanitSoundTimerSelect(cam_data)

    assert entity.current_option == "Continuous"
    assert cam_data.sound_timer_seconds is None
    assert entity.available is True


async def test_sound_timer_select_option_sets_seconds() -> None:
    coordinator = _push_coordinator(_camera_state())
    cam_data = _media_cam_data(coordinator, MagicMock(uid="cam_1"))
    entity = NanitSoundTimerSelect(cam_data)
    _disable_state_writes(entity)

    await entity.async_select_option("60 min")

    assert entity.current_option == "60 min"
    assert cam_data.sound_timer_seconds == 3600


async def test_media_player_set_volume_level_calls_set_settings_with_volume() -> None:
    coordinator = _push_coordinator(_camera_state())
    camera = MagicMock(uid="cam_1")
    camera.async_set_settings = AsyncMock()
    entity = NanitMediaPlayer(_media_cam_data(coordinator, camera))
    _disable_state_writes(entity)

    await entity.async_set_volume_level(0.42)

    camera.async_set_settings.assert_awaited_once_with(volume=42)


async def test_camera_entity_is_on_false_when_sleep_mode_enabled(
    hass: HomeAssistant,
) -> None:
    _ = await _resolve_hass(hass)
    coordinator = _push_coordinator(_camera_state(sleep_mode=True))
    camera = MagicMock(uid="cam_1")
    entity = NanitCameraEntity(coordinator, camera)

    assert entity.is_on is False


def test_camera_entity_is_on_true_when_sleep_mode_disabled() -> None:
    coordinator = _push_coordinator(_camera_state(sleep_mode=False))
    camera = MagicMock(uid="cam_1")
    entity = NanitCameraEntity(coordinator, camera)

    assert entity.is_on is True


async def test_camera_stream_source_returns_url_when_on() -> None:
    coordinator = _push_coordinator(_camera_state(sleep_mode=False))
    coordinator.config_entry.options = {}  # go2rtc disabled -> legacy RTMPS path
    camera = MagicMock(uid="cam_1")
    camera.async_get_stream_rtmps_url = AsyncMock(return_value="rtmps://stream-url")
    camera.async_start_streaming = AsyncMock()
    entity = NanitCameraEntity(coordinator, camera)

    source = await entity.stream_source()

    assert source == "rtmps://stream-url"
    camera.async_start_streaming.assert_awaited_once()


async def test_camera_stream_source_returns_none_when_camera_off() -> None:
    coordinator = _push_coordinator(_camera_state(sleep_mode=True))
    camera = MagicMock(uid="cam_1")
    camera.async_get_stream_rtmps_url = AsyncMock()
    camera.async_start_streaming = AsyncMock()
    entity = NanitCameraEntity(coordinator, camera)

    source = await entity.stream_source()

    assert source is None
    camera.async_get_stream_rtmps_url.assert_not_awaited()


async def test_camera_stream_source_returns_none_when_camera_api_fails() -> None:
    coordinator = _push_coordinator(_camera_state(sleep_mode=False))
    coordinator.config_entry.options = {}  # go2rtc disabled -> legacy RTMPS path
    camera = MagicMock(uid="cam_1")
    camera.async_get_stream_rtmps_url = AsyncMock(side_effect=RuntimeError("offline"))
    camera.async_start_streaming = AsyncMock()
    entity = NanitCameraEntity(coordinator, camera)

    source = await entity.stream_source()

    assert source is None


async def test_camera_start_streaming_safe_logs_failure_without_raising() -> None:
    coordinator = _push_coordinator(_camera_state(sleep_mode=False))
    camera = MagicMock(uid="cam_1")
    camera.async_start_streaming = AsyncMock(side_effect=RuntimeError("ws closed"))
    entity = NanitCameraEntity(coordinator, camera)

    with patch("custom_components.nanit.camera._STREAM_RETRY_DELAY", 0):
        result = await entity._async_start_streaming_safe()

    assert result is False
    assert camera.async_start_streaming.await_count == 3


@pytest.mark.asyncio
async def test_availability_grace_period_hides_brief_disconnect(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain="nanit", data={}, version=2, unique_id="test@example.com")
    entry.add_to_hass(hass)

    camera = MagicMock(uid="cam_1", baby_uid="baby_1")
    camera.connected = False
    camera.state = _camera_state(connection_state=ConnectionState.DISCONNECTED)
    camera.subscribe = MagicMock(return_value=lambda: None)
    camera.async_start = AsyncMock()
    camera.async_stop = AsyncMock()

    coordinator = NanitPushCoordinator(hass, entry, camera, MOCK_BABY_1)
    coordinator.connected = True

    cancel_timer = MagicMock()
    with patch(
        "custom_components.nanit.coordinator.async_call_later",
        return_value=cancel_timer,
    ) as mock_call_later:
        coordinator._on_camera_event(
            _MODELS.CameraEvent(
                kind=_MODELS.CameraEventKind.CONNECTION_CHANGE,
                state=_camera_state(connection_state=ConnectionState.DISCONNECTED),
            )
        )

    assert coordinator.connected is True
    mock_call_later.assert_called_once()
    assert mock_call_later.call_args.args[1] == _AVAILABILITY_GRACE_SECONDS
    assert coordinator._availability_timer is cancel_timer


@pytest.mark.asyncio
async def test_availability_grace_period_expires(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain="nanit", data={}, version=2, unique_id="test@example.com")
    entry.add_to_hass(hass)

    camera = MagicMock(uid="cam_1", baby_uid="baby_1")
    camera.connected = False
    camera.state = _camera_state(connection_state=ConnectionState.DISCONNECTED)
    camera.subscribe = MagicMock(return_value=lambda: None)
    camera.async_start = AsyncMock()
    camera.async_stop = AsyncMock()

    coordinator = NanitPushCoordinator(hass, entry, camera, MOCK_BABY_1)
    coordinator.connected = True
    coordinator.async_update_listeners = MagicMock()

    timeout_callback: Any | None = None

    def _capture_timer(_hass: HomeAssistant, _seconds: float, callback):
        nonlocal timeout_callback
        timeout_callback = callback
        return MagicMock()

    with patch(
        "custom_components.nanit.coordinator.async_call_later",
        side_effect=_capture_timer,
    ):
        coordinator._on_camera_event(
            _MODELS.CameraEvent(
                kind=_MODELS.CameraEventKind.CONNECTION_CHANGE,
                state=_camera_state(connection_state=ConnectionState.DISCONNECTED),
            )
        )

    assert coordinator.connected is True
    assert timeout_callback is not None
    baseline_calls = coordinator.async_update_listeners.call_count
    timeout_callback(None)
    assert coordinator.connected is False
    assert coordinator.async_update_listeners.call_count == baseline_calls + 1


@pytest.mark.asyncio
async def test_reconnect_within_grace_cancels_timer(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain="nanit", data={}, version=2, unique_id="test@example.com")
    entry.add_to_hass(hass)

    camera = MagicMock(uid="cam_1", baby_uid="baby_1")
    camera.connected = False
    camera.state = _camera_state(connection_state=ConnectionState.DISCONNECTED)
    camera.subscribe = MagicMock(return_value=lambda: None)
    camera.async_start = AsyncMock()
    camera.async_stop = AsyncMock()

    coordinator = NanitPushCoordinator(hass, entry, camera, MOCK_BABY_1)
    coordinator.connected = True
    coordinator.async_update_listeners = MagicMock()

    timeout_callback: Any | None = None
    cancel_timer = MagicMock()

    def _capture_timer(_hass: HomeAssistant, _seconds: float, callback):
        nonlocal timeout_callback
        timeout_callback = callback
        return cancel_timer

    with patch(
        "custom_components.nanit.coordinator.async_call_later",
        side_effect=_capture_timer,
    ):
        coordinator._on_camera_event(
            _MODELS.CameraEvent(
                kind=_MODELS.CameraEventKind.CONNECTION_CHANGE,
                state=_camera_state(connection_state=ConnectionState.DISCONNECTED),
            )
        )

    camera.connected = True
    coordinator._on_camera_event(
        _MODELS.CameraEvent(
            kind=_MODELS.CameraEventKind.CONNECTION_CHANGE,
            state=_camera_state(connection_state=ConnectionState.CONNECTED),
        )
    )

    assert coordinator.connected is True
    cancel_timer.assert_called_once()
    assert timeout_callback is not None
    baseline_calls = coordinator.async_update_listeners.call_count
    timeout_callback(None)
    assert coordinator.connected is True
    assert coordinator.async_update_listeners.call_count == baseline_calls


def test_camera_invalidates_stream_on_reconnection() -> None:
    from datetime import UTC, datetime

    t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC)

    coordinator = _push_coordinator(_camera_state(last_seen=t1))
    camera = MagicMock(uid="cam_1")
    entity = NanitCameraEntity(coordinator, camera)
    _disable_state_writes(entity)

    entity._handle_coordinator_update()
    assert entity._prev_last_seen == t1

    entity.stream = MagicMock()
    coordinator.data = _camera_state(last_seen=t2)
    entity._handle_coordinator_update()

    assert entity.stream is None
    assert entity._prev_last_seen == t2


def test_camera_does_not_invalidate_stream_when_last_seen_unchanged() -> None:
    from datetime import UTC, datetime

    t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    coordinator = _push_coordinator(_camera_state(last_seen=t1))
    camera = MagicMock(uid="cam_1")
    entity = NanitCameraEntity(coordinator, camera)
    _disable_state_writes(entity)

    entity._handle_coordinator_update()

    mock_stream = MagicMock()
    entity.stream = mock_stream
    coordinator.data = _camera_state(last_seen=t1)
    entity._handle_coordinator_update()

    assert entity.stream is mock_stream


def test_camera_does_not_invalidate_stream_on_first_update() -> None:
    from datetime import UTC, datetime

    t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    coordinator = _push_coordinator(_camera_state(last_seen=t1))
    camera = MagicMock(uid="cam_1")
    entity = NanitCameraEntity(coordinator, camera)
    _disable_state_writes(entity)

    mock_stream = MagicMock()
    entity.stream = mock_stream
    entity._handle_coordinator_update()

    assert entity.stream is mock_stream
    assert entity._prev_last_seen == t1


def test_camera_does_not_invalidate_when_no_stream_cached() -> None:
    from datetime import UTC, datetime

    t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 1, 1, 13, 0, 0, tzinfo=UTC)

    coordinator = _push_coordinator(_camera_state(last_seen=t1))
    camera = MagicMock(uid="cam_1")
    entity = NanitCameraEntity(coordinator, camera)
    _disable_state_writes(entity)

    entity._handle_coordinator_update()
    coordinator.data = _camera_state(last_seen=t2)
    entity._handle_coordinator_update()

    assert entity.stream is None
    assert entity._prev_last_seen == t2


async def test_start_breathing_button_presses_camera() -> None:
    """Pressing the button calls camera.async_start_breathing_tracking()."""
    camera = MagicMock()
    camera.uid = "cam_uid_1"
    camera.async_start_breathing_tracking = AsyncMock()
    button = NanitStartBreathingButton(_push_coordinator(_camera_state()), camera)
    await button.async_press()
    camera.async_start_breathing_tracking.assert_awaited_once()


async def test_start_breathing_button_surfaces_error() -> None:
    """A BreathingStartError from the camera surfaces as HomeAssistantError."""
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.nanit.aionanit.exceptions import BreathingStartError

    camera = MagicMock()
    camera.uid = "cam_uid_1"
    camera.async_start_breathing_tracking = AsyncMock(
        side_effect=BreathingStartError("no band detected")
    )
    button = NanitStartBreathingButton(_push_coordinator(_camera_state()), camera)
    with pytest.raises(HomeAssistantError):
        await button.async_press()


async def test_stream_source_uses_go2rtc_when_enabled_and_reachable(hass) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    from custom_components.nanit.camera import NanitCameraEntity
    from custom_components.nanit.const import CONF_GO2RTC_HOST, CONF_USE_GO2RTC

    coordinator = MagicMock()
    coordinator.config_entry.options = {CONF_USE_GO2RTC: True, CONF_GO2RTC_HOST: "hostx"}
    coordinator.data = None  # is_on defaults True
    camera = MagicMock()
    camera.uid = "CAM1"

    ent = NanitCameraEntity(coordinator, camera)
    ent.hass = hass
    with patch(
        "custom_components.nanit.camera.go2rtc.async_addon_reachable",
        AsyncMock(return_value=True),
    ):
        url = await ent.stream_source()
    assert url == "rtsp://hostx:18554/CAM1"


async def test_stream_source_falls_back_to_rtmps_when_unreachable(hass) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    from custom_components.nanit.camera import NanitCameraEntity
    from custom_components.nanit.const import CONF_GO2RTC_HOST, CONF_USE_GO2RTC

    coordinator = MagicMock()
    coordinator.config_entry.options = {CONF_USE_GO2RTC: True, CONF_GO2RTC_HOST: "hostx"}
    coordinator.data = None
    camera = MagicMock()
    camera.uid = "CAM1"
    camera.async_get_stream_rtmps_url = AsyncMock(return_value="rtmps://legacy/CAM1")

    ent = NanitCameraEntity(coordinator, camera)
    ent.hass = hass
    with (
        patch(
            "custom_components.nanit.camera.go2rtc.async_addon_reachable",
            AsyncMock(return_value=False),
        ),
        patch.object(ent, "_async_start_streaming_safe", AsyncMock(return_value=True)),
    ):
        url = await ent.stream_source()
    assert url == "rtmps://legacy/CAM1"


async def test_stream_source_rtmps_when_disabled(hass) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.nanit.camera import NanitCameraEntity

    coordinator = MagicMock()
    coordinator.config_entry.options = {}  # disabled
    coordinator.data = None
    camera = MagicMock()
    camera.uid = "CAM1"
    camera.async_get_stream_rtmps_url = AsyncMock(return_value="rtmps://legacy/CAM1")

    ent = NanitCameraEntity(coordinator, camera)
    ent.hass = hass
    ent._async_start_streaming_safe = AsyncMock(return_value=True)
    url = await ent.stream_source()
    assert url == "rtmps://legacy/CAM1"
