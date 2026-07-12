"""Select platform for Nanit — Sound & Light Machine sound."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import NanitConfigEntry
from .aionanit_sl.exceptions import NanitTransportError
from .const import DEFAULT_SOUND_MACHINE_SOUNDS
from .coordinator import NanitSoundLightCoordinator
from .entity import NanitEntity, NanitSoundLightEntity
from .hub import CameraData

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

# Auto-off timer presets for HA-initiated sound machine playback.
# Value is the playback duration in seconds; None uses the aionanit default
# (24h ~ continuous). Order defines the option order shown in the UI.
_TIMER_OPTIONS: dict[str, int | None] = {
    "Continuous": None,
    "15 min": 15 * 60,
    "30 min": 30 * 60,
    "45 min": 45 * 60,
    "60 min": 60 * 60,
}
_DEFAULT_TIMER_OPTION = "Continuous"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NanitConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Nanit select entities for all cameras on the account."""
    entities: list[SelectEntity] = []
    for cam_data in entry.runtime_data.cameras.values():
        entities.append(NanitSoundTimerSelect(cam_data))
        sl_coordinator = cam_data.sound_light_coordinator
        if sl_coordinator is not None:
            entities.append(NanitSoundSelect(sl_coordinator))
    async_add_entities(entities)


class NanitSoundSelect(NanitSoundLightEntity, SelectEntity):
    """Select entity to choose which sound the Sound & Light Machine plays."""

    _attr_translation_key = "sound_machine_sound"
    _attr_icon = "mdi:playlist-music"

    def __init__(
        self,
        coordinator: NanitSoundLightCoordinator,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        baby = coordinator.baby
        self._attr_unique_id = f"{baby.camera_uid}_sound_machine_sound"

    @property
    def options(self) -> list[str]:
        """Return available sound options from device state."""
        if self.coordinator.data is not None and self.coordinator.data.available_tracks:
            return list(self.coordinator.data.available_tracks)
        return [s.replace("_", " ").title() for s in DEFAULT_SOUND_MACHINE_SOUNDS]

    @property
    def current_option(self) -> str | None:
        """Return the currently selected sound track."""
        if self.coordinator.data is None:
            return None
        result: str | None = self.coordinator.data.current_track
        return result

    async def async_select_option(self, option: str) -> None:
        """Change the selected sound track via local WebSocket."""
        try:
            await self.coordinator.sound_light.async_set_track(option)
        except NanitTransportError as err:
            _LOGGER.error("Failed to set sound to %s: %s", option, err)


class NanitSoundTimerSelect(NanitEntity, RestoreEntity, SelectEntity):
    """Select the auto-off timer for HA-initiated sound machine playback.

    The Nanit app has its own per-track timer (e.g. 60 min) that HA cannot
    read or write. This entity instead picks how long playback *started from
    HA* runs before the camera stops it: the choice becomes the ``duration``
    of the next media player play/select-source command. It is a stored user
    preference, so it is always available regardless of camera connectivity.
    """

    _attr_translation_key = "sound_machine_timer"
    _attr_icon = "mdi:timer-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, cam_data: CameraData) -> None:
        """Initialize."""
        super().__init__(cam_data.push_coordinator)
        self._cam_data = cam_data
        self._attr_unique_id = f"{cam_data.camera.uid}_sound_machine_timer"
        self._attr_current_option = _DEFAULT_TIMER_OPTION
        cam_data.sound_timer_seconds = _TIMER_OPTIONS[_DEFAULT_TIMER_OPTION]

    @property
    def options(self) -> list[str]:
        """Return the available timer presets."""
        return list(_TIMER_OPTIONS)

    @property
    def available(self) -> bool:
        """Always available — this is a stored preference, not live device data."""
        return True

    async def async_added_to_hass(self) -> None:
        """Restore the previously selected timer option."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in _TIMER_OPTIONS:
            self._attr_current_option = last.state
            self._cam_data.sound_timer_seconds = _TIMER_OPTIONS[last.state]

    async def async_select_option(self, option: str) -> None:
        """Store the selected timer; applied to the next playback command."""
        self._attr_current_option = option
        self._cam_data.sound_timer_seconds = _TIMER_OPTIONS[option]
        self.async_write_ha_state()
