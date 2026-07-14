"""Tests for the go2rtc add-on helper (URL building + API push)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from multidict import CIMultiDict
from yarl import URL

from custom_components.nanit import go2rtc
from custom_components.nanit.const import (
    CONF_GO2RTC_HOST,
    CONF_USE_GO2RTC,
    DEFAULT_GO2RTC_HOST,
)


def test_webrtc_enabled_reads_options() -> None:
    assert go2rtc.webrtc_enabled(SimpleNamespace(options={CONF_USE_GO2RTC: True})) is True
    assert go2rtc.webrtc_enabled(SimpleNamespace(options={})) is False


def test_go2rtc_host_default_and_override() -> None:
    assert go2rtc.go2rtc_host(SimpleNamespace(options={})) == DEFAULT_GO2RTC_HOST
    assert (
        go2rtc.go2rtc_host(SimpleNamespace(options={CONF_GO2RTC_HOST: "192.168.68.107"}))
        == "192.168.68.107"
    )


def test_build_source_url_encodes() -> None:
    url = go2rtc.build_source_url("CAM1", "tok/with+special=chars")
    assert url.startswith("nanit:?")
    assert "camera_uid=CAM1" in url
    # token special chars must be percent-encoded, not raw
    assert "tok%2Fwith%2Bspecial%3Dchars" in url
    assert "tok/with+special=chars" not in url


def test_ingest_url() -> None:
    assert (
        go2rtc.ingest_url("192.168.68.107", "CAM1")
        == "webrtc:http://192.168.68.107:11984/api/webrtc?src=CAM1"
    )


async def test_async_push_stream_puts_correct_request() -> None:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.put = MagicMock(return_value=ctx)

    await go2rtc.async_push_stream(session, "hostx", "CAM1", "TOKEN")

    args, kwargs = session.put.call_args
    assert args[0] == "http://hostx:11984/api/streams"
    assert kwargs["params"]["name"] == "CAM1"
    assert kwargs["params"]["src"] == "nanit:?camera_uid=CAM1&access_token=TOKEN"
    resp.raise_for_status.assert_called_once()


async def test_async_push_stream_sanitizes_token_on_failure() -> None:
    """A push failure must never leak the access token via the raised exception.

    aiohttp's ClientResponseError stringifies to include the full request URL
    (query params and all) — which for us includes ``access_token=<TOKEN>``.
    `async_push_stream` must re-raise a sanitized error instead, with the
    original token-bearing exception unreachable via __cause__/__context__.
    """
    token = "SUPER-SECRET-TOKEN-VALUE"  # test sentinel, not a real secret
    src = go2rtc.build_source_url("CAM1", token)
    request_url = URL(f"http://hostx:11984/api/streams?src={src}")
    request_info = aiohttp.RequestInfo(
        url=request_url,
        method="PUT",
        headers=CIMultiDict(),
        real_url=request_url,
    )
    token_bearing_err = aiohttp.ClientResponseError(
        request_info=request_info,
        history=(),
        status=500,
        message="Internal Server Error",
    )
    # Sanity check on the fixture itself: the token really is present in the
    # original exception's string form (this is the leak we're guarding against).
    assert token in str(token_bearing_err)

    session = MagicMock()
    session.put = MagicMock(side_effect=token_bearing_err)

    with pytest.raises(Exception) as exc_info:
        await go2rtc.async_push_stream(session, "hostx", "CAM1", token)

    raised = exc_info.value
    assert token not in str(raised)
    assert "CAM1" in str(raised)
    assert raised.__cause__ is None
    assert raised.__context__ is None


async def test_async_push_stream_sanitizes_token_on_timeout() -> None:
    """A hung PUT must time out (not hang integration setup) and still not leak the token.

    Simulates a black-holed ``go2rtc_host`` (wrong IP/firewall DROP): the PUT
    never completes, so ``asyncio.timeout`` fires. The resulting TimeoutError
    is caught by the same broad ``except Exception`` and folded into the same
    sanitized RuntimeError as any other failure — no token, no chain.
    """
    token = "SUPER-SECRET-TOKEN-VALUE"  # test sentinel, not a real secret
    session = MagicMock()
    session.put = MagicMock(side_effect=TimeoutError())

    with pytest.raises(Exception) as exc_info:
        await go2rtc.async_push_stream(session, "hostx", "CAM1", token)

    raised = exc_info.value
    assert token not in str(raised)
    assert "CAM1" in str(raised)
    assert raised.__cause__ is None
    assert raised.__context__ is None


async def test_async_addon_reachable_true_false() -> None:
    ok_resp = MagicMock(status=200)
    ok_ctx = MagicMock()
    ok_ctx.__aenter__ = AsyncMock(return_value=ok_resp)
    ok_ctx.__aexit__ = AsyncMock(return_value=False)
    session_ok = MagicMock()
    session_ok.get = MagicMock(return_value=ok_ctx)
    assert await go2rtc.async_addon_reachable(session_ok, "hostx") is True

    session_bad = MagicMock()
    session_bad.get = MagicMock(side_effect=OSError("refused"))
    assert await go2rtc.async_addon_reachable(session_bad, "hostx") is False


async def test_async_get_frame_returns_bytes_on_200() -> None:
    resp = MagicMock()
    resp.status = 200
    resp.read = AsyncMock(return_value=b"\xff\xd8jpegbytes")
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=cm)

    out = await go2rtc.async_get_frame(session, "host9", "CAMX")

    assert out == b"\xff\xd8jpegbytes"
    url = session.get.call_args.args[0]
    assert url == "http://host9:11984/api/frame.jpeg?src=CAMX"


async def test_async_get_frame_raises_on_non_200() -> None:
    resp = MagicMock()
    resp.status = 500
    resp.read = AsyncMock(return_value=b"")
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=cm)

    with patch("custom_components.nanit.go2rtc.asyncio.sleep", AsyncMock()):
        with pytest.raises(RuntimeError):
            await go2rtc.async_get_frame(session, "host9", "CAMX")

    assert session.get.call_count == 3


async def test_async_get_frame_raises_on_transport_error() -> None:
    session = MagicMock()
    session.get = MagicMock(side_effect=aiohttp.ClientError("boom"))

    with patch("custom_components.nanit.go2rtc.asyncio.sleep", AsyncMock()):
        with pytest.raises(RuntimeError):
            await go2rtc.async_get_frame(session, "host9", "CAMX")

    assert session.get.call_count == 3


async def test_async_get_frame_retries_then_succeeds() -> None:
    """First call hits a transcode-corrupt 500, second call gets a good frame.

    Exercises the real retry path end-to-end: assert the actual returned
    bytes (not just that session.get was called twice).
    """
    fail_resp = MagicMock()
    fail_resp.status = 500
    fail_resp.read = AsyncMock(return_value=b"")
    fail_cm = MagicMock()
    fail_cm.__aenter__ = AsyncMock(return_value=fail_resp)
    fail_cm.__aexit__ = AsyncMock(return_value=False)

    ok_resp = MagicMock()
    ok_resp.status = 200
    ok_resp.read = AsyncMock(return_value=b"\xff\xd8jpegbytes")
    ok_cm = MagicMock()
    ok_cm.__aenter__ = AsyncMock(return_value=ok_resp)
    ok_cm.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.get = MagicMock(side_effect=[fail_cm, ok_cm])

    out = await go2rtc.async_get_frame(session, "host9", "CAMX", delay=0)

    assert out == b"\xff\xd8jpegbytes"
    assert session.get.call_count == 2


def test_lite_enabled_reads_options() -> None:
    from custom_components.nanit.const import CONF_LITE_CAMERA

    assert go2rtc.lite_enabled(SimpleNamespace(options={CONF_LITE_CAMERA: True})) is True
    assert go2rtc.lite_enabled(SimpleNamespace(options={})) is False


def test_lite_stream_name() -> None:
    assert go2rtc.lite_stream_name("CAM1") == "CAM1_lite"


def test_build_lite_source_url_transcodes_and_copies_audio() -> None:
    src = go2rtc.build_lite_source_url("CAM1")
    # Reads the parent 1080p stream by name — so the camera is opened only once,
    # and the source carries no access token.
    assert src.startswith("ffmpeg:CAM1#")
    assert "#video=h264" in src
    assert "#width=640" in src
    assert "#height=360" in src
    # Mandatory: go2rtc's ffmpeg source drops audio unless asked for.
    assert "#audio=copy" in src
    assert "access_token" not in src


def test_lite_ingest_url() -> None:
    assert (
        go2rtc.lite_ingest_url("192.168.68.107", "CAM1")
        == "webrtc:http://192.168.68.107:11984/api/webrtc?src=CAM1_lite"
    )


async def test_async_push_lite_stream_puts_correct_request() -> None:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=resp)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.put = MagicMock(return_value=ctx)

    await go2rtc.async_push_lite_stream(session, "hostx", "CAM1")

    args, kwargs = session.put.call_args
    assert args[0] == "http://hostx:11984/api/streams"
    assert kwargs["params"]["name"] == "CAM1_lite"
    assert kwargs["params"]["src"] == go2rtc.build_lite_source_url("CAM1")
    resp.raise_for_status.assert_called_once()


async def test_async_push_lite_stream_swallows_failure() -> None:
    """A lite-stream failure must never take down the 1080p camera."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(side_effect=aiohttp.ClientError("boom"))
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.put = MagicMock(return_value=ctx)

    # Returns normally — no exception propagates.
    assert await go2rtc.async_push_lite_stream(session, "hostx", "CAM1") is None
