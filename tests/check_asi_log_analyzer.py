from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from analyze_asi_log import analyze_log  # noqa: E402


def main() -> None:
    fixture = """\
[12:00:00.000] SHADER_OBJECT_CREATED stage=VS object=00001000 profile=VS_3_0 bytes=96 hash=aaa111 hr=0x00000000
[12:00:00.001] SHADER_OBJECT_CREATED stage=PS object=00002000 profile=PS_2_0 bytes=128 hash=bbb222 hr=0x00000000
[12:00:00.0015] SHADER_FALLBACK_OBJECT_MAP object=00002000 source_hash=ccc333 target_hash=bbb222 target_profile=ps_2_0
[12:00:00.002] DRAW_CALL seq=1 frame=4 kind=DrawIndexedPrimitive device=00003000 primitive=4 primitives=12 start_vertex=0 base_vertex=0 min_vertex=0 num_vertices=36 start_index=0 bound_vs=00001000 bound_ps=00002000 hr=0x00000000
[12:00:00.003] DRAW_CALL seq=2 frame=4 kind=DrawIndexedPrimitive device=00003000 primitive=4 primitives=4 start_vertex=0 base_vertex=0 min_vertex=0 num_vertices=12 start_index=36 bound_vs=00001000 bound_ps=00002000 hr=0x00000000
[12:00:00.004] DRAW_CALL seq=3 frame=5 kind=DrawPrimitive device=00003000 primitive=4 primitives=2 start_vertex=0 base_vertex=0 min_vertex=0 num_vertices=6 start_index=0 bound_vs=00001000 bound_ps=00009999 hr=0x80004005
[12:00:00.005] DEVICE_PRESENT_FAILED hr=0x88760868
[12:00:00.006] DEVICE_RESET_RESULT hr=0x88760868
"""
    with tempfile.TemporaryDirectory() as temporary:
        log_path = Path(temporary) / "IVLegacy.log"
        log_path.write_text(fixture, encoding="utf-8")
        report = analyze_log(log_path)

    assert report["shader_objects_observed"] == 2
    assert report["draw_calls_observed"] == 3
    assert report["successful_draw_calls"] == 2
    assert report["failed_draw_calls"] == 1
    assert report["present_failures"] == 1
    assert report["reset_failures"] == 1
    assert report["frames_observed"] == 2
    assert report["unresolved_shader_references"] == 1

    top = report["shader_pair_usage"][0]
    assert top["draw_calls"] == 2
    assert top["primitive_submissions"] == 16
    assert top["vertex_shader_hash"] == "aaa111"
    assert top["pixel_shader_hash"] == "bbb222"
    assert top["frames"] == [4]
    fallback = report["shader_fallback_usage"][0]
    assert fallback["source_shader_hash"] == "ccc333"
    assert fallback["replacement_shader_hash"] == "bbb222"
    assert fallback["draw_calls"] == 2
    assert fallback["primitive_submissions"] == 16

    vs = next(x for x in report["shader_usage"] if x["shader_key"] == "VS:aaa111")
    assert vs["draw_calls"] == 3

    print("PASS: IVLegacy log parser correlates shader objects, hashes and D3D9 draws")


if __name__ == "__main__":
    main()
