"""Constants for the Nanit integration."""

import logging

from homeassistant.const import Platform

DOMAIN = "nanit"
LOGGER = logging.getLogger(__package__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.MEDIA_PLAYER,
    Platform.CAMERA,
    Platform.BUTTON,
]

# Cloud event detection window (seconds)
CLOUD_EVENT_WINDOW = 300

# Breathing (STING) staleness window (seconds). The camera pushes a
# PUT_STING_STATUS frame every ~4-5s while tracking is active and simply stops
# when the session ends, so a reading older than this means monitoring is off
# and the breathing entities report unavailable rather than a stale value.
BREATHING_STALE_AFTER = 30

# Cloud event poll interval (seconds)
CLOUD_POLL_INTERVAL = 30

# Network info poll interval (seconds)
NETWORK_POLL_INTERVAL = 300

# Config Keys
CONF_MFA_CODE = "mfa_code"
CONF_MFA_TOKEN = "mfa_token"
CONF_STORE_CREDENTIALS = "store_credentials"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_BABY_UID = "baby_uid"
CONF_CAMERA_UID = "camera_uid"
CONF_BABY_NAME = "baby_name"
CONF_CAMERA_IP = "camera_ip"
CONF_CAMERA_IPS = "camera_ips"
CONF_SPEAKER_UID = "speaker_uid"
CONF_SPEAKER_IP = "speaker_ip"
CONF_SPEAKER_IPS = "speaker_ips"
# Cameras on the account that the integration must not connect to — e.g. one that
# is never plugged in. Without this, every setup waits out the connect timeout for
# it, raises a repair issue, and delays Home Assistant's startup.
# CONF_IGNORE_CAMERA is the per-camera checkbox in the options flow;
# CONF_IGNORED_CAMERAS is the stored list of camera UIDs.
CONF_IGNORE_CAMERA = "ignore_camera"
CONF_IGNORED_CAMERAS = "ignored_cameras"

# Default sound list (used when API doesn't return available_sounds)
DEFAULT_SOUND_MACHINE_SOUNDS = (
    "white_noise",
    "birds",
    "waves",
    "wind",
    "rain",
    "water_stream",
    "fan",
    "heartbeat",
    "dryer",
    "vacuum",
)

# --- go2rtc WebRTC add-on wiring ---
CONF_USE_GO2RTC = "use_go2rtc"
CONF_GO2RTC_HOST = "go2rtc_host"
GO2RTC_API_PORT = 11984
# The add-on's RTSP listener. Deliberately NOT 18554 — that is HA's bundled
# go2rtc's RTSP port, so binding there makes the add-on's listener fail and any
# rtsp:// ingest silently hit the wrong server.
GO2RTC_RTSP_PORT = 18654
DEFAULT_GO2RTC_HOST = "homeassistant.local"

# Downscaled companion stream for low-power displays (e.g. an old kiosk tablet
# that cannot decode 1080p). This is a go2rtc `ffmpeg:` source that reads the
# camera's *existing* 1080p stream by name, so the camera is still opened only
# once and the transcode runs only while someone is watching the lite stream.
# `#audio=copy` is mandatory: go2rtc's ffmpeg source drops audio unless asked,
# and the source OPUS is passed through untouched.
#
# Software encode on purpose (no `#hardware=...`). The template used to force
# `#hardware=vaapi`, which only works where the go2rtc add-on can open /dev/dri.
# When HA moved into a KVM guest (2026-11-12) there was no GPU, ffmpeg exited
# with "No device available for decoder: device type vaapi needed", and the lite
# stream served empty frames. A 640x360 x264 encode is cheap on any modern CPU.
CONF_LITE_CAMERA = "lite_camera"
GO2RTC_LITE_SOURCE_TEMPLATE = "ffmpeg:{camera_uid}#video=h264#width=640#height=360#audio=copy"
