"""Tests for STING (Breathing Motion Monitoring) status parsing."""

from __future__ import annotations

from typing import Any

from custom_components.nanit.aionanit.models import BreathingState
from custom_components.nanit.aionanit.parsers import _parse_sting_status
from custom_components.nanit.aionanit.proto import Request, RequestType, StingStatus

# A real PUT_STING_STATUS field-23 payload captured from a Nanit Pro camera with
# Breathing Wear active. Ground-truthed: field 10 (breaths_per_minute) read 43,
# matching the app's displayed value at capture time; mode (field 11) was GREEN.
_REAL_FRAME = (
    b"\x08\x02\x10\x01\x18\x01 \x00*\x06\x08\xf3\x04\x10\xad\x032\x06\x08\xf3\x04"
    b"\x10\xad\x03@\xb0\xdb\xc2\xd2\x06J\x19N301CMN22474TX_1783672150P+X\x00b\n"
    b"A3hGte6wfoh\x86\x04p\xd6\xda\xc2\xd2\x06\x88\x01\x00\x95\x01\xf8\xc1#@\x9d"
    b"\x01\x90\x1e{@"
)


def _sting_request(**kwargs: Any) -> Request:
    return Request(
        id=1,
        type=RequestType.PUT_STING_STATUS,
        sting_status=StingStatus(**kwargs),
    )


def test_parses_breaths_per_minute_and_mode() -> None:
    result = _parse_sting_status(
        _sting_request(
            state=2,
            server_connected=True,
            mode=0,
            breathing=1,
            breaths_per_minute=43,
        )
    )
    assert isinstance(result, BreathingState)
    assert result.breaths_per_minute == 43
    assert result.is_alert is False
    assert result.mode == 0
    assert result.breathing == 1
    assert result.received_at is not None


def test_alert_flag_true() -> None:
    result = _parse_sting_status(_sting_request(mode=2, breaths_per_minute=40))
    assert result is not None
    assert result.is_alert is True


def test_zero_bpm_normalised_to_none() -> None:
    result = _parse_sting_status(_sting_request(breaths_per_minute=0, mode=0))
    assert result is not None
    assert result.breaths_per_minute is None


def test_returns_none_without_sting_status() -> None:
    assert _parse_sting_status(Request(id=1, type=RequestType.PUT_STING_STATUS)) is None


def test_returns_none_for_non_request() -> None:
    assert _parse_sting_status(object()) is None


def test_parse_sting_status_alert_from_mode_red() -> None:
    from custom_components.nanit.aionanit.proto import nanit_pb2

    req = nanit_pb2.Request(id=1, type=nanit_pb2.RequestType.PUT_STING_STATUS)
    req.sting_status.mode = 2  # RED
    req.sting_status.breathing = 4  # NO_BREATHING
    req.sting_status.breaths_per_minute = 0
    state = _parse_sting_status(req)
    assert state is not None
    assert state.is_alert is True
    assert state.mode == 2
    assert state.breathing == 4
    assert state.breaths_per_minute is None  # 0 normalised


def test_parse_sting_status_healthy_session_is_not_alert() -> None:
    """The bug: a calm session (server_connected on, mode GREEN) must NOT alert."""
    from custom_components.nanit.aionanit.proto import nanit_pb2

    req = nanit_pb2.Request(id=1, type=nanit_pb2.RequestType.PUT_STING_STATUS)
    req.sting_status.server_connected = True
    req.sting_status.mode = 0  # GREEN
    req.sting_status.breathing = 1  # NORMAL
    req.sting_status.breaths_per_minute = 43
    state = _parse_sting_status(req)
    assert state is not None
    assert state.is_alert is False
    assert state.breaths_per_minute == 43
    assert state.breathing == 1


def test_parses_real_captured_frame() -> None:
    request = Request()
    request.ParseFromString(
        Request(
            id=1,
            type=RequestType.PUT_STING_STATUS,
            sting_status=StingStatus.FromString(_REAL_FRAME),
        ).SerializeToString()
    )
    result = _parse_sting_status(request)
    assert result is not None
    assert result.breaths_per_minute == 43
    assert result.is_alert is False
    assert result.mode == 0
    assert result.breathing == 1
