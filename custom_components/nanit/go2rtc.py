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
    CONF_USE_GO2RTC,
    DEFAULT_GO2RTC_HOST,
    GO2RTC_API_PORT,
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
