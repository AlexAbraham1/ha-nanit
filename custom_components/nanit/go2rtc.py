"""Helper for the forked-go2rtc WebRTC add-on.

Builds the ``nanit:`` source URL, points the camera at the add-on's stream, and
pushes fresh access tokens to the add-on's go2rtc API so the stream never
expires. The Go source itself is unchanged; this module only *talks* to it.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlencode

import aiohttp

from .const import (
    CONF_GO2RTC_HOST,
    CONF_LITE_CAMERA,
    CONF_USE_GO2RTC,
    DEFAULT_GO2RTC_HOST,
    GO2RTC_API_PORT,
    GO2RTC_LITE_SOURCE_TEMPLATE,
    LOGGER,
)


def webrtc_enabled(entry: Any) -> bool:
    """Return True if the go2rtc WebRTC add-on path is enabled in options."""
    return bool(entry.options.get(CONF_USE_GO2RTC, False))


def go2rtc_host(entry: Any) -> str:
    """Return the configured add-on host (hostname or IP, no scheme/port)."""
    return str(entry.options.get(CONF_GO2RTC_HOST, DEFAULT_GO2RTC_HOST))


def build_source_url(camera_uid: str, access_token: str) -> str:
    """Build the go2rtc ``nanit:`` source URL for a camera (URL-encoded)."""
    query = urlencode({"camera_uid": camera_uid, "access_token": access_token})
    return f"nanit:?{query}"


def ingest_url(host: str, camera_uid: str) -> str:
    """Return the URL HA's built-in go2rtc ingests for this camera.

    Uses the go2rtc-to-go2rtc ``webrtc:`` transport (not RTSP). Verified on the
    box: the add-on's RTSP server binds 127.0.0.1 only (unreachable across
    containers) and RTSP dropped the media, whereas the ``webrtc:`` source pulls
    H264 video + OPUS audio intact from the add-on. ``GO2RTC_RTSP_PORT`` is kept
    for reference/diagnostics only.
    """
    return f"webrtc:http://{host}:{GO2RTC_API_PORT}/api/webrtc?src={camera_uid}"


async def async_push_stream(
    session: aiohttp.ClientSession, host: str, camera_uid: str, access_token: str
) -> None:
    """Create/update the camera's stream in the add-on's go2rtc via its API.

    NOTE: the request URL/params embed the access token (via ``build_source_url``).
    aiohttp exceptions (e.g. ``ClientResponseError``) stringify to include the
    full request URL, so any failure here is re-raised as a sanitized
    ``RuntimeError`` with no token and no source URL — and with the token-bearing
    original exception deliberately left unchained (raised outside the ``except``
    block), so it can't leak back out via ``exc_info``/``__cause__``/``__context__``.
    """
    url = f"http://{host}:{GO2RTC_API_PORT}/api/streams"
    params = {"name": camera_uid, "src": build_source_url(camera_uid, access_token)}
    sanitized_error: RuntimeError | None = None
    try:
        async with asyncio.timeout(5):
            async with session.put(url, params=params) as resp:
                resp.raise_for_status()
    except Exception as err:  # noqa: BLE001 - deliberately broad: sanitize before re-raising
        status = getattr(err, "status", "?")
        sanitized_error = RuntimeError(f"go2rtc push failed for {camera_uid} (status {status})")
    if sanitized_error is not None:
        # Raised *outside* the except block (not `raise ... from err`/`from None`)
        # so it picks up no implicit exception chain at all: both __cause__ and
        # __context__ end up None, meaning the token-bearing original exception
        # (which stringifies with the full request URL, token included) is not
        # reachable from this exception even via exc_info/traceback internals.
        raise sanitized_error
    LOGGER.debug("Pushed go2rtc stream for camera %s via %s", camera_uid, host)


async def async_addon_reachable(session: aiohttp.ClientSession, host: str) -> bool:
    """Return True if the add-on's go2rtc API answers within a short timeout."""
    url = f"http://{host}:{GO2RTC_API_PORT}/api/streams"
    try:
        async with asyncio.timeout(2):
            async with session.get(url) as resp:
                return resp.status == 200
    except (TimeoutError, aiohttp.ClientError, OSError) as err:
        LOGGER.debug("go2rtc add-on unreachable at %s: %s", host, err)
        return False


async def async_get_frame(
    session: aiohttp.ClientSession,
    host: str,
    camera_uid: str,
    *,
    attempts: int = 3,
    delay: float = 0.7,
) -> bytes:
    """Return a JPEG still from the add-on's live feed for a camera.

    GETs go2rtc's ``/api/frame.jpeg`` (which renders a keyframe via the add-on's
    ffmpeg). The frame URL carries no access token, so — unlike
    ``async_push_stream`` — no exception sanitization is needed.

    go2rtc's transcode intermittently lands on a corrupt/non-keyframe H264
    frame and returns a 500 (``exit status 183``); this is transient, so on a
    non-200 or a transport error we retry up to ``attempts`` times, sleeping
    ``delay`` seconds between attempts so a fresh keyframe can arrive. Raises
    the most recent ``RuntimeError`` if every attempt fails.
    """
    url = f"http://{host}:{GO2RTC_API_PORT}/api/frame.jpeg?src={camera_uid}"
    last_error: RuntimeError | None = None
    for attempt in range(attempts):
        try:
            async with asyncio.timeout(10):
                async with session.get(url) as resp:
                    if resp.status != 200:
                        last_error = RuntimeError(
                            f"go2rtc frame fetch failed for {camera_uid} (status {resp.status})"
                        )
                    else:
                        return await resp.read()
        except (TimeoutError, aiohttp.ClientError, OSError) as err:
            last_error = RuntimeError(f"go2rtc frame fetch failed for {camera_uid}: {err}")
        if attempt < attempts - 1:
            await asyncio.sleep(delay)
    assert last_error is not None  # attempts >= 1, so the loop always sets this
    raise last_error


def lite_enabled(entry: Any) -> bool:
    """Return True if the downscaled companion camera is enabled in options."""
    return bool(entry.options.get(CONF_LITE_CAMERA, False))


def lite_stream_name(camera_uid: str) -> str:
    """Return the add-on's go2rtc stream name for the downscaled companion stream."""
    return f"{camera_uid}_lite"


def build_lite_source_url(camera_uid: str) -> str:
    """Build the go2rtc transcode source for the downscaled companion stream.

    The source reads the camera's *existing* 1080p go2rtc stream by name, so it
    carries no access token — which is why ``async_push_lite_stream`` needs none
    of the exception sanitization ``async_push_stream`` does.
    """
    return GO2RTC_LITE_SOURCE_TEMPLATE.format(camera_uid=camera_uid)


def lite_ingest_url(host: str, camera_uid: str) -> str:
    """Return the URL HA's built-in go2rtc ingests for the companion stream."""
    return ingest_url(host, lite_stream_name(camera_uid))


async def async_push_lite_stream(
    session: aiohttp.ClientSession, host: str, camera_uid: str
) -> None:
    """Create/update the camera's downscaled companion stream in the add-on.

    Must be called *after* ``async_push_stream`` for the same camera: the source
    resolves the parent 1080p stream by name, so the parent must already exist.

    Unlike ``async_push_stream``, neither the request URL nor the source carries
    an access token, so the underlying exception is safe to log — but a failure
    here must never take down the 1080p camera, so it is logged and swallowed.
    """
    url = f"http://{host}:{GO2RTC_API_PORT}/api/streams"
    params = {"name": lite_stream_name(camera_uid), "src": build_lite_source_url(camera_uid)}
    try:
        async with asyncio.timeout(5):
            async with session.put(url, params=params) as resp:
                resp.raise_for_status()
    except (TimeoutError, aiohttp.ClientError, OSError) as err:
        LOGGER.warning("Failed to push go2rtc lite stream for %s: %s", camera_uid, err)
        return
    LOGGER.debug("Pushed go2rtc lite stream for camera %s via %s", camera_uid, host)
