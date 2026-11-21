from pathlib import Path
import math
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from analyze_asi_constants import (  # noqa: E402
    ConstantCaptureError,
    analyze_directory,
    parse_capture,
)


HEADER = struct.Struct("<4sHHIIIII")


def write_capture(path: Path, stage: int, frame: int, sequence: int,
                  start: int, vectors: list[tuple[float, float, float, float]]) -> None:
    flat = [value for vector in vectors for value in vector]
    payload = struct.pack(f"<{len(flat)}f", *flat)
    header = HEADER.pack(
        b"IVCF", 1, stage, frame, sequence, start,
        len(vectors), len(payload)
    )
    path.write_bytes(header + payload)


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        vs_path = directory / "VS_000001.bin"
        ps_path = directory / "PS_000002.bin"
        write_capture(vs_path, 0, 3, 1, 4, [(1.0, 2.0, 3.0, 4.0)])
        write_capture(ps_path, 1, 3, 2, 7, [(0.25, 0.5, 0.75, 1.0)])

        vs = parse_capture(vs_path)
        assert vs["stage"] == "VS"
        assert vs["frame_index"] == 3
        assert vs["registers"][0]["register"] == 4
        assert vs["registers"][0]["xyzw"] == [1.0, 2.0, 3.0, 4.0]

        report = analyze_directory(directory)
        assert report["record_count"] == 2
        assert report["invalid_record_count"] == 0
        assert report["stage_counts"] == {"VS": 1, "PS": 1}
        assert report["frame_indices"] == [3]

        bad_path = directory / "bad.bin"
        bad_path.write_bytes(b"BAD!" + vs_path.read_bytes()[4:])
        try:
            parse_capture(bad_path)
        except ConstantCaptureError:
            pass
        else:
            raise AssertionError("bad magic must be rejected")

        bad_range_path = directory / "bad_range.bin"
        write_capture(bad_range_path, 1, 3, 3, 255, [(1.0, 2.0, 3.0, 4.0), (5.0, 6.0, 7.0, 8.0)])
        try:
            parse_capture(bad_range_path)
        except ConstantCaptureError:
            pass
        else:
            raise AssertionError("register range past c255 must be rejected")

    print("PASS: D3D9 shader constant sidecar parser validates headers, ranges and float values")


if __name__ == "__main__":
    main()
