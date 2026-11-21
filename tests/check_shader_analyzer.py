from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from analyze_d3d9_shaders import (  # noqa: E402
    ShaderParseError,
    analyze_shader_bytes,
    make_parameter_token,
)


def pack(*words):
    import struct
    return struct.pack("<" + "I" * len(words), *words)


def main():
    # A comment block must be skipped by its token-declared DWORD count.
    comment_shader = pack(
        0xFFFF0200,
        0x0002FFFE, 0x12345678, 0x9ABCDEF0,
        0x0000FFFF,
    )
    report = analyze_shader_bytes(comment_shader, "comment.ps")
    assert report["comment_block_count"] == 1
    assert report["comment_payload_dwords"] == 2
    assert report["trailing_dwords_after_end"] == 0

    # A vertex shader must be identified separately from a pixel shader.
    vertex_shader = pack(
        0xFFFE0300,
        (2 << 24) | 1,
        make_parameter_token(0, 31),
        make_parameter_token(1, 0),
        0x0000FFFF,
    )
    report = analyze_shader_bytes(vertex_shader, "vertex.vs")
    assert report["stage"] == "VS"
    assert report["profile"] == "vs_3_0"
    assert report["highest_temporary_register"] == 31

    for invalid in (b"", pack(0x12340200, 0x0000FFFF), pack(0xFFFF0101, 0x0000FFFF)):
        try:
            analyze_shader_bytes(invalid, "invalid.bin")
        except ShaderParseError:
            continue
        raise AssertionError("invalid shader stream was accepted")

    print("PASS: shader inventory parser integration checks")


if __name__ == "__main__":
    main()
