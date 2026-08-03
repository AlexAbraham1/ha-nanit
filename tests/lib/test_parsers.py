"""Tests for aionanit.parsers — sensor-data decoding."""

from __future__ import annotations

from custom_components.nanit.aionanit.models import SensorState
from custom_components.nanit.aionanit.parsers import _parse_sensor_data
from custom_components.nanit.aionanit.proto import SensorData, SensorType


def _parse(*sensor_data: SensorData, current: SensorState | None = None) -> SensorState:
    return _parse_sensor_data(list(sensor_data), current or SensorState())


class TestSensorFaultSentinel:
    """The camera reports -1000 when its temp/humidity chip fails to read.

    Published verbatim that surfaces as -1768 °F / -1000 % on the dashboard,
    which reads as a real measurement instead of "no data".
    """

    def test_temperature_sentinel_becomes_none(self) -> None:
        state = _parse(SensorData(sensor_type=SensorType.TEMPERATURE, value_milli=-1_000_000))
        assert state.temperature is None

    def test_humidity_sentinel_becomes_none(self) -> None:
        state = _parse(SensorData(sensor_type=SensorType.HUMIDITY, value_milli=-1_000_000))
        assert state.humidity is None

    def test_sentinel_in_plain_value_field_becomes_none(self) -> None:
        state = _parse(SensorData(sensor_type=SensorType.TEMPERATURE, value=-1000))
        assert state.temperature is None

    def test_sentinel_clears_a_previously_good_reading(self) -> None:
        """A fault must not leave the last good value pinned indefinitely."""
        current = SensorState(temperature=21.5, humidity=52.4)
        state = _parse(
            SensorData(sensor_type=SensorType.TEMPERATURE, value_milli=-1_000_000),
            SensorData(sensor_type=SensorType.HUMIDITY, value_milli=-1_000_000),
            current=current,
        )
        assert state.temperature is None
        assert state.humidity is None

    def test_light_is_unaffected_by_the_sentinel(self) -> None:
        """Light is a separate subsystem and keeps reporting through the fault."""
        state = _parse(
            SensorData(sensor_type=SensorType.TEMPERATURE, value_milli=-1_000_000),
            SensorData(sensor_type=SensorType.LIGHT, value=234),
        )
        assert state.temperature is None
        assert state.light == 234


class TestNormalReadings:
    def test_real_values_pass_through(self) -> None:
        state = _parse(
            SensorData(sensor_type=SensorType.TEMPERATURE, value_milli=21_500),
            SensorData(sensor_type=SensorType.HUMIDITY, value_milli=52_400),
        )
        assert state.temperature == 21.5
        assert state.humidity == 52.4

    def test_legitimate_negative_temperature_is_kept(self) -> None:
        """Only the exact sentinel is rejected — real sub-zero readings stand."""
        state = _parse(SensorData(sensor_type=SensorType.TEMPERATURE, value_milli=-5_000))
        assert state.temperature == -5.0
