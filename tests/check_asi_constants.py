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


HEADER_V1 = struct.Struct("<4sHHIIIII")
HEADER_V2 = struct.Struct("<4sHHIIIIII")


def write_capture(path: Path, stage: int, frame: int, sequence: int,
                  start: int, vectors: list[tuple[float, float, float, float]],
                  shader_object: int = 0x1234ABCD) -> None:
    flat = [value for vector in vectors for value in vector]
    payload = struct.pack(f"<{len(flat)}f", *flat)
    header = HEADER_V2.pack(
        b"IVCF", 2, stage, frame, shader_object, sequence, start,
        len(vectors), len(payload)
    )
    path.write_bytes(header + payload)


def write_v1_capture(path: Path) -> None:
    values = (9.0, 8.0, 7.0, 6.0)
    payload = struct.pack("<4f", *values)
    header = HEADER_V1.pack(b"IVCF", 1, 0, 2, 9, 1, 1, len(payload))
    path.write_bytes(header + payload)

def write_typed_capture(path: Path, magic: bytes, stage: int, frame: int,
                        sequence: int, start: int, values: tuple[int, ...],
                        shader_object: int = 0x1234ABCD) -> None:
    payload = struct.pack(f"<{len(values)}{'i' if magic == b'IVCI' else 'I'}", *values)
    header = HEADER_V2.pack(
        magic, 2, stage, frame, shader_object, sequence,
        start, len(values) if magic == b"IVCB" else len(values) // 4,
        len(payload)
    )
    path.write_bytes(header + payload)


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        vs_path = directory / "VS_000001.bin"
        ps_path = directory / "PS_000002.bin"
        write_capture(vs_path, 0, 3, 1, 4, [(1.0, 2.0, 3.0, 4.0)])
        write_capture(ps_path, 1, 3, 2, 7, [(0.25, 0.5, 0.75, 1.0)], shader_object=0xABCDEF01)
        legacy_path = directory / "VS_legacy_v1.bin"
        write_v1_capture(legacy_path)
        vs_int_path = directory / "VS_integer.bin"
        ps_int_path = directory / "PS_integer.bin"
        vs_bool_path = directory / "VS_boolean.bin"
        ps_bool_path = directory / "PS_boolean.bin"
        write_typed_capture(vs_int_path, b"IVCI", 0, 3, 3, 2, (1, -2, 3, -4))
        write_typed_capture(ps_int_path, b"IVCI", 1, 3, 4, 1, (-5, 6, -7, 8), shader_object=0xABCDEF01)
        write_typed_capture(vs_bool_path, b"IVCB", 0, 3, 5, 4, (0, 1))
        write_typed_capture(ps_bool_path, b"IVCB", 1, 3, 6, 5, (1, 0), shader_object=0xABCDEF01)

        vs = parse_capture(vs_path)
        assert vs["stage"] == "VS"
        assert vs["frame_index"] == 3
        assert vs["registers"][0]["register"] == 4
        assert vs["registers"][0]["xyzw"] == [1.0, 2.0, 3.0, 4.0]
        assert vs["version"] == 2
        assert vs["shader_object"] == "1234ABCD"
        ps = parse_capture(ps_path)
        assert ps["shader_object"] == "ABCDEF01"
        legacy = parse_capture(legacy_path)
        assert legacy["version"] == 1
        assert legacy["shader_object"] is None
        assert legacy["registers"][0]["xyzw"] == [9.0, 8.0, 7.0, 6.0]
        vs_int = parse_capture(vs_int_path)
        assert vs_int["data_kind"] == "int"
        assert vs_int["registers"][0]["xyzw"] == [1, -2, 3, -4]
        ps_bool = parse_capture(ps_bool_path)
        assert ps_bool["data_kind"] == "bool"
        assert ps_bool["registers"][0]["enabled"] is True
        assert ps_bool["registers"][1]["enabled"] is False

        log_path = directory / "IVLegacy.log"
        log_path.write_text(
            "[12:00:00.000] SHADER_OBJECT_CREATED stage=VS object=1234ABCD profile=VS_3_0 bytes=96 hash=aaa111 hr=0x00000000\n"
            "[12:00:00.001] SHADER_OBJECT_CREATED stage=PS object=ABCDEF01 profile=PS_2_0 bytes=64 hash=bbb222 hr=0x00000000\n"
            "[12:00:00.002] SHADER_FALLBACK_OBJECT_MAP object=ABCDEF01 source_hash=ccc333 target_hash=bbb222 target_profile=ps_2_0\n",
            encoding="utf-8",
        )
        report = analyze_directory(directory, log_path)
        assert report["record_count"] == 7
        assert report["invalid_record_count"] == 0
        assert report["stage_counts"] == {"VS": 4, "PS": 3}
        assert report["frame_indices"] == [2, 3]
        assert report["shader_objects_resolved"] == 6

        vs_sidecar = next(record for record in report["records"] if record["stage"] == "VS" and record["version"] == 2)
        ps_sidecar = next(record for record in report["records"] if record["stage"] == "PS")
        assert vs_sidecar["shader_profile"] == "vs_3_0"
        assert vs_sidecar["shader_bytecode_hash"] == "aaa111"
        assert ps_sidecar["shader_profile"] == "ps_2_0"
        assert ps_sidecar["shader_bytecode_hash"] == "bbb222"
        assert ps_sidecar["source_shader_hash"] == "ccc333"

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

    print("PASS: D3D9 float, integer and boolean constant sidecars validate and resolve to shader hashes")


if __name__ == "__main__":
    main()
