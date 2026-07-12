"""Proto round-trip: StingStart / Point / Area under Request.sting_start (tag 22)."""

from __future__ import annotations

from custom_components.nanit.aionanit.proto import (
    Area,
    Point,
    Request,
    RequestType,
    StingStart,
)


def test_sting_start_roundtrip() -> None:
    req = Request(
        id=7,
        type=RequestType.PUT_STING_START,
        sting_start=StingStart(
            win_location=Point(x=150, y=60),
            session_id="abc-uuid",
            remote_server="",
            enable_baby_not_in_bed=True,
        ),
    )
    back = Request.FromString(req.SerializeToString())
    assert back.HasField("sting_start")
    assert back.sting_start.win_location.x == 150
    assert back.sting_start.win_location.y == 60
    assert back.sting_start.session_id == "abc-uuid"
    assert back.sting_start.remote_server == ""
    assert back.sting_start.enable_baby_not_in_bed is True


def test_sting_start_is_wire_field_22() -> None:
    req = Request(
        id=1,
        type=RequestType.PUT_STING_START,
        sting_start=StingStart(session_id="x"),
    )
    raw = req.SerializeToString()
    # tag = (22 << 3) | 2 (length-delimited) = 178 -> varint bytes 0xB2 0x01
    assert b"\xb2\x01" in raw


def test_area_message_importable() -> None:
    a = Area(width=12, height=34)
    assert (a.width, a.height) == (12, 34)
