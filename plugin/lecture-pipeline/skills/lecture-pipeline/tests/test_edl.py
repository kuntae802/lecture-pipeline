from lecture_pipeline.edl import keep_segments, write_render_script


def test_keep_segments_is_complement_of_cuts():
    assert keep_segments(100.0, [(10.0, 12.0), (20.0, 25.0)]) == [(0.0, 10.0), (12.0, 20.0), (25.0, 100.0)]
    assert keep_segments(100.0, []) == [(0.0, 100.0)]
    assert keep_segments(100.0, [(0.0, 5.0)]) == [(5.0, 100.0)]          # 시작 컷
    assert keep_segments(100.0, [(90.0, 100.0)]) == [(0.0, 90.0)]        # 끝 컷


def test_render_script_mentions_every_segment_and_concat():
    sh = write_render_script([(0.0, 10.0), (12.0, 20.0)], "/in/01.mp4", "/out/01.edited.mp4", "/work", encoder="h264_nvenc")
    assert sh.count("-ss ") == 2 and "h264_nvenc" in sh and "concat" in sh and "afade" in sh
    assert "-to 10.000" in sh and "-ss 12.000" in sh
    assert "seg_0000.mp4" in sh and "seg_0001.mp4" in sh and "/out/01.edited.mp4" in sh


def test_render_script_cpu_encoder():
    sh = write_render_script([(0.0, 10.0)], "/in/01.mp4", "/out/o.mp4", "/work", encoder="libx264")
    assert "libx264" in sh and "nvenc" not in sh
