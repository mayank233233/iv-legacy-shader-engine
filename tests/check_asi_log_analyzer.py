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
[12:00:00.0016] TEXTURE_OBJECT_CREATED type=2D object=00004000 width=64 height=32 levels=1 usage=0x00000000 format=21 pool=1 hr=0x00000000
[12:00:00.0017] SET_SAMPLER_STATE sampler=0 type=2 value=3 hr=0x00000000
[12:00:00.0018] SET_RENDER_STATE state=15 value=1 hr=0x00000000
[12:00:00.0019] SET_TEXTURE_STAGE_STATE stage=0 state=1 value=4 hr=0x00000000
[12:00:00.00195] VERTEX_DECL_OBJECT_CREATED object=00006000 hr=0x00000000
[12:00:00.00196] VERTEX_DECL_ELEMENT object=00006000 index=0 stream=0 offset=0 type=2 method=0 usage=0 usage_index=0
[12:00:00.00197] VERTEX_DECL_ELEMENT object=00006000 index=1 stream=0 offset=12 type=1 method=0 usage=5 usage_index=0
[12:00:00.00198] BUFFER_OBJECT_CREATED type=VB object=00005000 length=4096 usage=0x00000008 fvf=0x00000000 pool=1 hr=0x00000000
[12:00:00.00199] BUFFER_OBJECT_CREATED type=IB object=00007000 length=1024 usage=0x00000008 format=101 pool=1 hr=0x00000000
[12:00:00.002] DRAW_CALL seq=1 frame=4 kind=DrawIndexedPrimitive device=00003000 primitive=4 primitives=12 start_vertex=0 base_vertex=0 min_vertex=0 num_vertices=36 start_index=0 bound_vs=00001000 bound_ps=00002000 vertex_decl=00006000 fvf=0x00000000 index_buffer=00007000 streams=0:00005000:0:20:1 textures=0:00004000;1:00000000 sampler_hash=abcdef0123456789 sampler_count=1 render_state_hash=12345678 render_state_count=1 texture_stage_hash=87654321 texture_stage_count=1 hr=0x00000000
[12:00:00.003] DRAW_CALL seq=2 frame=4 kind=DrawIndexedPrimitive device=00003000 primitive=4 primitives=4 start_vertex=0 base_vertex=0 min_vertex=0 num_vertices=12 start_index=36 bound_vs=00001000 bound_ps=00002000 textures=0:00004000;1:00000000 sampler_hash=abcdef0123456789 hr=0x00000000
[12:00:00.004] DRAW_CALL seq=3 frame=5 kind=DrawPrimitive device=00003000 primitive=4 primitives=2 start_vertex=0 base_vertex=0 min_vertex=0 num_vertices=6 start_index=0 bound_vs=00001000 bound_ps=00009999 hr=0x80004005
[12:00:00.0045] SHADER_OBJECT_CREATED stage=PS object=00002000 profile=PS_3_0 bytes=72 hash=ddd444 hr=0x00000000
[12:00:00.0048] DRAW_CALL seq=4 frame=6 kind=DrawPrimitive device=00003000 primitive=4 primitives=1 start_vertex=0 base_vertex=0 min_vertex=0 num_vertices=3 start_index=0 bound_vs=00001000 bound_ps=00002000 hr=0x00000000
[12:00:00.005] DEVICE_PRESENT_FAILED hr=0x88760868
[12:00:00.006] DEVICE_RESET_RESULT hr=0x88760868
"""
    with tempfile.TemporaryDirectory() as temporary:
        log_path = Path(temporary) / "IVLegacy.log"
        log_path.write_text(fixture, encoding="utf-8")
        report = analyze_log(log_path)

    assert report["shader_objects_observed"] == 2
    assert report["draw_calls_observed"] == 4
    assert report["successful_draw_calls"] == 3
    assert report["failed_draw_calls"] == 1
    assert report["present_failures"] == 1
    assert report["reset_failures"] == 1
    assert report["frames_observed"] == 3
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
    assert report["texture_objects_observed"] == 1
    texture = report["texture_object_usage"][0]
    assert texture["object"] == "4000"
    assert texture["descriptor"]["width"] == 64
    assert texture["descriptor"]["height"] == 32
    assert texture["draw_calls"] == 2
    assert report["draw_calls"][0]["sampler_state_hash"] == "abcdef0123456789"
    assert report["draw_calls"][0]["sampler_state_count"] == 1
    assert report["draw_calls"][0]["render_state_hash"] == "12345678"
    assert report["draw_calls"][0]["render_state_count"] == 1
    assert report["draw_calls"][0]["texture_stage_state_hash"] == "87654321"
    assert report["draw_calls"][0]["texture_stage_state_count"] == 1
    assert report["draw_calls"][0]["texture_bindings"][0]["descriptor"]["format"] == 21
    assert report["vertex_declarations_observed"] == 1
    vertex_decl = report["draw_calls"][0]["vertex_declaration"]
    assert vertex_decl["object"] == "6000"
    assert vertex_decl["elements"][0]["usage"] == 0
    assert vertex_decl["elements"][1]["offset"] == 12
    assert report["draw_calls"][0]["index_buffer_object"] == "7000"
    assert report["buffer_objects_observed"] == 2
    assert report["draw_calls"][0]["index_buffer"]["length_bytes"] == 1024
    assert report["draw_calls"][0]["index_buffer"]["format"] == 101
    assert report["draw_calls"][0]["stream_bindings"][0]["buffer_descriptor"]["length_bytes"] == 4096
    assert report["draw_calls"][0]["stream_bindings"][0]["buffer_descriptor"]["type"] == "VB"
    assert report["draw_calls"][0]["stream_bindings"][0] == {
        "stream": 0, "buffer": "5000", "offset": 0, "stride": 20, "frequency": 1
    }
    assert report["draw_calls"][3]["pixel_shader_fallback"] is None
    assert report["draw_calls"][3]["pixel_shader_key"] == "PS:ddd444"

    vs = next(x for x in report["shader_usage"] if x["shader_key"] == "VS:aaa111")
    assert vs["draw_calls"] == 4

    print("PASS: IVLegacy log parser correlates shader objects, hashes and D3D9 draws")


if __name__ == "__main__":
    main()
