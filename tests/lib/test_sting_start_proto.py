"""Proto round-trip: StingStart / Point / Area under Request.sting_start (tag 22)."""

from __future__ import annotations

from pathlib import Path

from custom_components.nanit.aionanit.proto import (
    Area,
    Point,
    Request,
    RequestType,
    StingStart,
    nanit_pb2,
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


def test_gencode_pinned_to_6_30_0_for_ha_runtime() -> None:
    """Guard the SHIPPED nanit_pb2.py against an unpinned regen.

    The HA box's protobuf runtime is 6.32.0. protoc stamps generated files with
    whatever protobuf version is installed on the dev machine, and a file stamped
    7.x+ raises at import time via ValidateProtobufRuntimeVersion() on that older
    runtime. tools/generate_proto.py patches the generated file down to a pinned
    floor (6, 30, 0) that HA's runtime satisfies. This test reads the *committed*
    artifact directly (not the patching logic) so a future regen that ships an
    unpinned file fails CI immediately instead of breaking the box at import time.
    """
    source = Path(nanit_pb2.__file__).read_text()

    assert "_runtime_version.Domain.PUBLIC, 6, 30, 0," in source
    assert "Domain.PUBLIC, 7," not in source
    assert "Domain.PUBLIC, 8," not in source
    assert "# Protobuf Python Version: 6.30.0" in source
