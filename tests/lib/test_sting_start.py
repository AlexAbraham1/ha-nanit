"""The real start-breathing flow: snapshot -> pattern POST -> PUT_STING_START."""

from __future__ import annotations

import dataclasses
import time
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.nanit.aionanit.auth import TokenManager
from custom_components.nanit.aionanit.camera import NanitCamera
from custom_components.nanit.aionanit.exceptions import (
    BreathingStartError,
    NanitCameraUnavailable,
)
from custom_components.nanit.aionanit.proto import RequestType, Response
from custom_components.nanit.aionanit.rest import NanitRestClient
from custom_components.nanit.aionanit.ws.protocol import decode_message

_BMM_URL = "https://api.nanit.com/focus/babies/baby_uid_1/bmm/sessions"
_GOOD_BOX = {"x1": "100", "x2": "200", "y1": "40", "y2": "80"}


def _make_camera() -> NanitCamera:
    session = MagicMock(spec=aiohttp.ClientSession)
    rest = MagicMock(spec=NanitRestClient)
    tm = MagicMock(spec=TokenManager)
    tm.async_get_access_token = AsyncMock(return_value="test_token")
    tm._expires_at = time.monotonic() + 3600.0
    return NanitCamera(
        uid="cam_uid_1",
        baby_uid="baby_uid_1",
        token_manager=tm,
        rest_client=rest,
        session=session,
    )


def _resp(status: int, *, read: bytes | None = None, json: object | None = None) -> MagicMock:
    r = MagicMock()
    r.status = status
    if read is not None:
        r.read = AsyncMock(return_value=read)
    if json is not None:
        r.json = AsyncMock(return_value=json)
    return r


def _pattern_payload(box: dict[str, str] | None = None, *, detected: bool = True) -> dict:
    session: dict = {"detected": detected}
    if detected:
        session["data"] = {"objects": [{"box": box or _GOOD_BOX, "score": "0.9"}]}
    return {"bmm_sessions": session}


def _form_fields(form: aiohttp.FormData) -> dict[str, object]:
    # aiohttp FormData stores (options, headers, value) tuples in _fields.
    return {opts["name"]: value for opts, _headers, value in form._fields}


def _wire_transport(cam: NanitCamera) -> list[bytes]:
    sent: list[bytes] = []
    cam._transport = MagicMock()
    cam._transport.connected = True
    cam._transport.idle_seconds = 0.0
    resp = Response(request_id=1, request_type=RequestType.PUT_STING_START, status_code=200)

    async def _fake_send(data: bytes) -> None:
        sent.append(data)
        cam._pending.resolve(1, resp)

    cam._transport.async_send = AsyncMock(side_effect=_fake_send)
    return sent


@pytest.mark.asyncio
async def test_full_flow_sends_sting_start_with_midpoint() -> None:
    cam = _make_camera()
    cam._session.post = AsyncMock(return_value=_resp(200, json=_pattern_payload()))
    sent = _wire_transport(cam)

    await cam.async_start_breathing_tracking(b"\xff\xd8jpeg")

    # POST targeted the BMM endpoint with token-prefix auth + rgb status.
    args, kwargs = cam._session.post.call_args
    assert args[0] == _BMM_URL
    assert kwargs["headers"]["Authorization"] == "token test_token"
    fields = _form_fields(kwargs["data"])
    assert fields["camera_status"] == "rgb"
    assert "image" in fields

    # ws send carried the computed midpoint (150, 60) and required fields.
    assert len(sent) == 1
    msg = decode_message(sent[0])
    assert msg.request.type == RequestType.PUT_STING_START
    assert msg.request.sting_start.win_location.x == 150
    assert msg.request.sting_start.win_location.y == 60
    assert msg.request.sting_start.enable_baby_not_in_bed is True
    assert msg.request.sting_start.remote_server == ""
    assert len(msg.request.sting_start.session_id) == 36  # uuid4


@pytest.mark.asyncio
async def test_raises_when_not_detected() -> None:
    cam = _make_camera()
    cam._session.post = AsyncMock(return_value=_resp(200, json=_pattern_payload(detected=False)))
    cam._transport = MagicMock()
    cam._transport.connected = True
    cam._transport.idle_seconds = 0.0
    cam._transport.async_send = AsyncMock()

    with pytest.raises(BreathingStartError):
        await cam.async_start_breathing_tracking(b"jpeg")
    cam._transport.async_send.assert_not_called()


@pytest.mark.asyncio
async def test_raises_on_http_error() -> None:
    cam = _make_camera()
    cam._session.post = AsyncMock(return_value=_resp(500, json={}))

    with pytest.raises(BreathingStartError):
        await cam.async_start_breathing_tracking(b"jpeg")


@pytest.mark.asyncio
async def test_raises_on_empty_objects() -> None:
    cam = _make_camera()
    cam._session.post = AsyncMock(
        return_value=_resp(200, json={"bmm_sessions": {"detected": True, "data": {"objects": []}}})
    )

    with pytest.raises(BreathingStartError):
        await cam.async_start_breathing_tracking(b"jpeg")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("box", "expected"),
    [
        ({"x1": "0", "x2": "10", "y1": "0", "y2": "20"}, (5, 10)),
        ({"x1": "100", "x2": "201", "y1": "40", "y2": "81"}, (150, 60)),  # floor division
    ],
)
async def test_midpoint_math(box: dict[str, str], expected: tuple[int, int]) -> None:
    cam = _make_camera()
    cam._session.post = AsyncMock(return_value=_resp(200, json=_pattern_payload(box)))
    point = await cam._request_breathing_pattern(b"jpeg")
    assert (point.x, point.y) == expected


@pytest.mark.asyncio
async def test_raises_on_malformed_box_bad_value() -> None:
    cam = _make_camera()
    box = {"x1": "bad", "x2": "200", "y1": "40", "y2": "80"}
    cam._session.post = AsyncMock(return_value=_resp(200, json=_pattern_payload(box)))

    with pytest.raises(BreathingStartError):
        await cam._request_breathing_pattern(b"jpeg")


@pytest.mark.asyncio
async def test_raises_on_malformed_box_missing_key() -> None:
    cam = _make_camera()
    box = {"x1": "100", "x2": "200"}  # missing y1/y2
    cam._session.post = AsyncMock(return_value=_resp(200, json=_pattern_payload(box)))

    with pytest.raises(BreathingStartError):
        await cam._request_breathing_pattern(b"jpeg")


@pytest.mark.asyncio
async def test_raises_on_post_network_error() -> None:
    cam = _make_camera()
    cam._session.post = AsyncMock(side_effect=aiohttp.ClientError("boom"))

    with pytest.raises(BreathingStartError):
        await cam._request_breathing_pattern(b"jpeg")


@pytest.mark.asyncio
async def test_raises_when_camera_send_fails() -> None:
    cam = _make_camera()
    cam._session.post = AsyncMock(return_value=_resp(200, json=_pattern_payload()))
    cam._send_request = AsyncMock(side_effect=NanitCameraUnavailable("camera offline"))

    with pytest.raises(BreathingStartError):
        await cam.async_start_breathing_tracking(b"jpeg")


@pytest.mark.asyncio
async def test_raises_on_non_json_response() -> None:
    resp = MagicMock()
    resp.status = 200
    resp.json = AsyncMock(side_effect=ValueError("not json"))
    cam = _make_camera()
    cam._session.post = AsyncMock(return_value=resp)

    with pytest.raises(BreathingStartError):
        await cam._request_breathing_pattern(b"jpeg")


@pytest.mark.asyncio
async def test_camera_status_ir_when_night() -> None:
    cam = _make_camera()
    # NOTE: night mode lives on CameraState.sensors.night, not a top-level
    # CameraState.night field (the brief's literal `night=True` on
    # `cam._state` raises TypeError — CameraState has no such field).
    cam._state = dataclasses.replace(
        cam._state, sensors=dataclasses.replace(cam._state.sensors, night=True)
    )
    cam._session.post = AsyncMock(return_value=_resp(200, json=_pattern_payload()))
    await cam._request_breathing_pattern(b"jpeg")
    fields = _form_fields(cam._session.post.call_args.kwargs["data"])
    assert fields["camera_status"] == "ir"
