from pathlib import Path

from lecture_pipeline import render


def test_segment_cmd_puts_seek_before_input_and_fades_at_boundaries():
    cmd = render._segment_cmd(Path("/in/src.mp4"), 10.0, 13.0, Path("/w/seg_0000.mp4"), "libx264")
    # -ss/-to 는 -i 앞에 있어야 빠른 탐색이 된다(뒤에 두면 전체를 디코딩한다)
    assert cmd.index("-ss") < cmd.index("-i") and cmd.index("-to") < cmd.index("-i")
    assert cmd[cmd.index("-ss") + 1] == "10.000" and cmd[cmd.index("-to") + 1] == "13.000"
    af = cmd[cmd.index("-af") + 1]
    assert af.startswith(f"afade=t=in:st=0:d={render.FADE}")
    assert f"afade=t=out:st={3.0 - render.FADE:.3f}" in af          # 구간 길이 3초 − 페이드 0.08초
    assert "libx264" in cmd and "h264_nvenc" not in cmd


def test_segment_cmd_short_segment_does_not_produce_negative_fade_start():
    cmd = render._segment_cmd(Path("a.mp4"), 0.0, 0.05, Path("s.mp4"), "h264_nvenc")
    af = cmd[cmd.index("-af") + 1]
    assert "afade=t=out:st=0.000" in af
    assert "h264_nvenc" in cmd


def test_pick_encoder_explicit_choice_is_passed_through(monkeypatch):
    monkeypatch.setattr(render, "nvenc_usable", lambda: True)
    assert render.pick_encoder("libx264") == "libx264"
    assert render.pick_encoder("h264_nvenc") == "h264_nvenc"


def test_pick_encoder_auto_prefers_cpu_when_cores_are_plentiful(monkeypatch):
    # 실측 근거: 코어가 많으면 x264 가 NVENC 보다 빠르고 파일도 작다 → GPU 가 있어도 CPU 를 쓴다
    monkeypatch.setattr(render.os, "cpu_count", lambda: 32)
    monkeypatch.setattr(render, "nvenc_usable", lambda: True)
    assert render.pick_encoder("auto") == "libx264"


def test_pick_encoder_auto_uses_gpu_on_small_machines_only_if_it_really_works(monkeypatch):
    monkeypatch.setattr(render.os, "cpu_count", lambda: 4)
    monkeypatch.setattr(render, "nvenc_usable", lambda: True)
    assert render.pick_encoder("auto") == "h264_nvenc"
    monkeypatch.setattr(render, "nvenc_usable", lambda: False)
    assert render.pick_encoder("auto") == "libx264"


def test_nvenc_probe_is_cached_and_falls_back_when_encoder_absent(monkeypatch):
    monkeypatch.setattr(render, "_NVENC_CACHE", None)
    monkeypatch.setattr(render, "has_encoder", lambda name: False)
    calls = []
    monkeypatch.setattr(render.subprocess, "run", lambda *a, **k: calls.append(a) or None)
    assert render.nvenc_usable() is False
    assert calls == []          # 목록에 없으면 인코딩 프로브를 아예 시도하지 않는다
    assert render.nvenc_usable() is False   # 캐시


def test_concat_list_uses_bare_filenames_so_quotes_in_paths_cannot_break_it():
    segs = [Path("/home/o'brien/작업 폴더/seg_0000.mp4"), Path("/home/o'brien/작업 폴더/seg_0001.mp4")]
    text = render.concat_list_text(segs)
    assert text == "file 'seg_0000.mp4'\nfile 'seg_0001.mp4'\n"
    assert "o'brien" not in text          # 경로가 목록에 들어가지 않으므로 따옴표 문제가 생길 수 없다
