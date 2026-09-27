import json

from lecture_pipeline import fetch


def _fake_run(calls, tmp):
    def run(cmd, check):
        calls.append(cmd)
        out = next(a for a in cmd if a.endswith("source.%(ext)s")).replace("source.%(ext)s", "")
        if "--skip-download" in cmd:
            (tmp / "raw/abcdefghijk/source.ko.json3").write_text("{}", encoding="utf-8")
            (tmp / "raw/abcdefghijk/source.info.json").write_text(json.dumps({"title": "t"}), encoding="utf-8")
        else:
            (tmp / "raw/abcdefghijk/source.mp4").write_bytes(b"x")
    return run


def test_text_mode_downloads_only_subtitles(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(fetch.subprocess, "run", _fake_run(calls, tmp_path))
    fetch.fetch("https://youtu.be/abcdefghijk", tmp_path / "raw")
    assert len(calls) == 1 and "--skip-download" in calls[0]
    assert not (tmp_path / "raw/abcdefghijk/source.mp4").exists()
    assert json.loads((tmp_path / "workspace/.job").read_text())["mode"] == "text"


def test_video_mode_also_downloads_the_video(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(fetch.subprocess, "run", _fake_run(calls, tmp_path))
    fetch.fetch("https://youtu.be/abcdefghijk", tmp_path / "raw", video=True)
    assert len(calls) == 2 and "--merge-output-format" in calls[1]
    assert json.loads((tmp_path / "workspace/.job").read_text())["mode"] == "video"
