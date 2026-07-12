"""Button platform for Nanit."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import NanitConfigEntry
from .aionanit.camera import NanitCamera
from .aionanit.exceptions import BreathingStartError
from .coordinator import NanitPushCoordinator
from .entity import NanitEntity

PARALLEL_UPDATES = 0


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
        """Send PUT_STING_START to the camera."""
        try:
            await self._camera.async_start_breathing_tracking()
        except BreathingStartError as err:
            raise HomeAssistantError(f"Could not start breathing monitoring: {err}") from err
