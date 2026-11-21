from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from analyze_constant_captures import (  # noqa: E402
    ConstantCaptureError,
    analyze_directory,
    parse_capture,
)

HEADER = struct.Struct("<4sHHIIIII")


def make_capture(stage: int, frame: int, sequence: int,
                 start: int, vectors: list[tuple[float, float, float, float]]) -> bytes:
    payload = struct.pack(
        "<" + "f" * (len(vectors) * 4),
        *(value for vector in vectors for value in vector),
    )
    return HEADER.pack(
        b"IVCF", 1, stage, frame, sequence, start, len(vectors), len(payload)
    ) + payload


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        (directory / "VS_000001.bin").write_bytes(
            make_capture(0, 3, 1, 4, [(1.0, 2.0, 3.0, 4.0)])
        )
        (directory / "PS_000002.bin").write_bytes(
            make_capture(1, 3, 2, 12, [(0.25, 0.5, 0.75, 1.0),
                                      (2.0, 3.0, 4.0, 5.0)])
        )

        report = analyze_directory(directory)
        assert report["file_count"] == 2
        assert report["valid_capture_count"] == 2
        assert report["invalid_capture_count"] == 0
        assert report["stage_counts"] == {"VS": 1, "PS": 1}
        assert report["frame_counts"] == {"3": 2}
        assert report["captures"][0]["stage"] == "VS"
        assert report["captures"][0]["registers"][0] == {
            "register": 4, "value": [1.0, 2.0, 3.0, 4.0]
        }
        assert report["captures"][1]["vector_count"] == 2
        assert report["captures"][1]["registers"][1]["register"] == 13

        bad = directory / "BAD.bin"
        bad.write_bytes(make_capture(2, 1, 1, 0, [(0.0, 0.0, 0.0, 0.0)]))
        try:
            parse_capture(bad)
        except ConstantCaptureError:
            pass
        else:
            raise AssertionError("unknown shader stage must be rejected")

    print("PASS: D3D9 constant sidecar parser validates VS/PS records and register ranges")


if __name__ == "__main__":
    main()
