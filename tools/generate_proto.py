#!/usr/bin/env python3
"""Generate google protobuf Python code from nanit.proto."""

import re
import subprocess
import sys
from pathlib import Path

PROTO_DIR = Path(__file__).parent / "proto"
OUT_DIR = Path(__file__).parent.parent / "custom_components" / "nanit" / "aionanit" / "proto"

# The Home Assistant box's protobuf runtime lags behind whatever protoc happens to be
# installed on the dev machine (HA has shipped protobuf 6.32.0 while dev machines may
# have 7.x+). protoc always stamps the generated file with the *local* protoc's gencode
# version, and google.protobuf.runtime_version.ValidateProtobufRuntimeVersion() raises
# at import time if the installed runtime is older than that stamped version. Since the
# serialized DESCRIPTOR bytes themselves are version-independent (only this one check
# is affected), we pin the declared gencode version down to a floor that HA's runtime
# satisfies, regardless of which protoc generated the file.
PINNED_GENCODE_VERSION = (6, 30, 0)

_VERSION_COMMENT_RE = re.compile(r"^# Protobuf Python Version: .*$", re.MULTILINE)
_VALIDATE_CALL_RE = re.compile(r"_runtime_version\.Domain\.PUBLIC,\s*\d+,\s*\d+,\s*\d+,")
_VALIDATE_LINE_RE = re.compile(
    r"^_runtime_version\.ValidateProtobufRuntimeVersion\(\s*$", re.MULTILINE
)

_EXPLANATION_COMMENT = (
    "# Gencode version lowered to 6.30.0 for compatibility with Home Assistant's\n"
    "# protobuf runtime (which may ship an older 6.x version than the dev machine).\n"
    "# The serialized DESCRIPTOR is version-independent; only this check is affected.\n"
)


def _pin_gencode_version(text: str) -> str:
    """Rewrite a freshly-generated nanit_pb2.py to pin its declared gencode version.

    protoc stamps the file with whatever protobuf version is installed locally. HA's
    runtime is often an older 6.x release, and the generated ValidateProtobufRuntimeVersion
    call raises on import if the runtime is older than the stamped version. This patch
    lowers the stamped version to a floor (6.30.0) that HA's runtime satisfies, and
    (re-)inserts the explanatory comment block a naive regen would otherwise drop.
    """
    major, minor, patch = PINNED_GENCODE_VERSION

    text, version_comment_count = _VERSION_COMMENT_RE.subn(
        f"# Protobuf Python Version: {major}.{minor}.{patch}", text, count=1
    )
    if version_comment_count == 0:
        raise RuntimeError(
            "generate_proto: could not pin gencode version — version comment regex "
            "did not match; protoc output format may have changed"
        )

    text, validate_call_count = _VALIDATE_CALL_RE.subn(
        f"_runtime_version.Domain.PUBLIC, {major}, {minor}, {patch},", text, count=1
    )
    if validate_call_count == 0:
        raise RuntimeError(
            "generate_proto: could not pin gencode version — validate call regex "
            "did not match; protoc output format may have changed"
        )

    if _EXPLANATION_COMMENT not in text:
        text = _VALIDATE_LINE_RE.sub(
            _EXPLANATION_COMMENT + "_runtime_version.ValidateProtobufRuntimeVersion(",
            text,
            count=1,
        )

    return text


def main() -> None:
    """Run protoc with --python_out to generate nanit_pb2.py."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{PROTO_DIR}",
        f"--python_out={OUT_DIR}",
        str(PROTO_DIR / "nanit.proto"),
    ]

    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    if result.returncode != 0:
        sys.exit(result.returncode)

    # protoc --python_out generates nanit_pb2.py directly in OUT_DIR.
    generated = OUT_DIR / "nanit_pb2.py"
    if generated.exists():
        generated.write_text(_pin_gencode_version(generated.read_text()))
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
