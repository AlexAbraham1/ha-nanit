"""Button platform for Nanit."""

from __future__ import annotations

from io import BytesIO

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from PIL import Image

from . import NanitConfigEntry, go2rtc
from .aionanit.camera import NanitCamera
from .aionanit.exceptions import BreathingStartError
from .coordinator import NanitPushCoordinator
from .entity import NanitEntity

PARALLEL_UPDATES = 0


def _jpeg_to_png(jpeg: bytes) -> bytes:
    """Convert a JPEG frame to PNG.

    Nanit's breathing-pattern API rejects JPEG with HTTP 422
    ("image must be a png file") — it only accepts PNG, as the app sends.
    """
    with Image.open(BytesIO(jpeg)) as img:
        buf = BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NanitConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Nanit buttons for all cameras on the account."""
    entities: list[ButtonEntity] = []
    for cam_data in entry.runtime_data.cameras.values():
        entities.append(NanitStartBreathingButton(cam_data.push_coordinator, cam_data.camera))
    async_add_entities(entities)


class NanitStartBreathingButton(NanitEntity, ButtonEntity):
    """Start a Breathing Motion Monitoring session (mirrors the app's start).

    One-shot: the camera stops tracking on its own when the baby leaves the
    crib, so there is no stop button. Display/convenience only — the Nanit app
    remains the safety-critical breathing-alert path.
    """

    _attr_translation_key = "start_breathing_tracking"
    _attr_icon = "mdi:lungs"

    def __init__(self, coordinator: NanitPushCoordinator, camera: NanitCamera) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._camera = camera
        self._attr_unique_id = f"{camera.uid}_start_breathing_tracking"

    async def async_press(self) -> None:
        """Fetch a still from the go2rtc add-on, then send PUT_STING_START."""
        entry = self.coordinator.config_entry
        if not go2rtc.webrtc_enabled(entry):
            raise HomeAssistantError(
                "The go2rtc add-on must be enabled to start breathing monitoring"
            )
        host = go2rtc.go2rtc_host(entry)
        session = async_get_clientsession(self.hass)
        try:
            frame = await go2rtc.async_get_frame(session, host, self._camera.uid)
        except RuntimeError as err:
            raise HomeAssistantError(
                f"Could not capture a camera frame for breathing monitoring: {err}"
            ) from err
        try:
            png = await self.hass.async_add_executor_job(_jpeg_to_png, frame)
        except Exception as err:  # any decode/encode failure
            raise HomeAssistantError(f"Could not convert the camera frame to PNG: {err}") from err
        try:
            await self._camera.async_start_breathing_tracking(png)
        except BreathingStartError as err:
            raise HomeAssistantError(f"Could not start breathing monitoring: {err}") from err
