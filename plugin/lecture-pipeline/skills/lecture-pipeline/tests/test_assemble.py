import json

import pytest

from lecture_pipeline.assemble import build_lecture
from lecture_pipeline.schema import validate_lecture


def _build(tmp_path):
    b = tmp_path / "build"
    b.mkdir()
    words = [{"start": i * 1.0, "end": i * 1.0 + 0.9, "text": f"w{i+1}", "type": "word"} for i in range(12)]
    sents = [{"idx": 1, "start": 0.0, "end": 3.9, "text": "w1 w2 w3 w4", "word_from": 1, "word_to": 4},
             {"idx": 2, "start": 4.0, "end": 7.9, "text": "w5 w6 w7 w8", "word_from": 5, "word_to": 8},
             {"idx": 3, "start": 8.0, "end": 11.9, "text": "w9 w10 w11 w12", "word_from": 9, "word_to": 12}]
    (b / "words.json").write_text(json.dumps({"source": "youtube_json3", "words": words}), encoding="utf-8")
    (b / "sentences.json").write_text(json.dumps(sents), encoding="utf-8")
    (b / "cuts.json").write_text(json.dumps([{"id": 1, "from_idx": 5, "to_idx": 8, "orig": [4.0, 7.9], "category": "duplicate",
                                              "confidence": "high", "removed_text": "w5 w6 w7 w8", "note": "n"}]), encoding="utf-8")
    (b / "corrections.json").write_text(json.dumps([{"idx": 10, "from": "w10", "to": "W10"}]), encoding="utf-8")
    return b


OUTLINE = {"chapters": [{"id": "1", "title": "A", "summary": "s", "segments": [1, 3],
                         "children": [{"id": "1.1", "title": "a", "summary": "t", "segments": [1, 1]},
                                      {"id": "1.2", "title": "b", "summary": "u", "segments": [2, 3]}]}]}
NOTES = {"commands": [{"text": "uv run x", "segment_idx": 3}], "links": [{"url": "https://x.y", "label": "x", "segment_idx": 1}]}
INFO = {"title": "T", "id": "vid", "webpage_url": "https://youtu.be/vid", "duration": 12}


def test_build_lecture_maps_times_applies_corrections_and_validates(tmp_path):
    b = _build(tmp_path)
    doc = build_lecture(b, OUTLINE, NOTES, INFO, edited_duration=8.1)
    assert validate_lecture(doc) == []
    assert doc["lecture"]["duration"] == {"orig": 12.0, "edit": 8.1}
    assert doc["segments"][1]["t"]["edit"] is None                               # 컷 안 문장
    assert doc["segments"][2]["t"]["edit"] == [4.1, 8.0] and "W10" in doc["segments"][2]["text"]
    assert doc["segments"][1]["text"] == "w5 w6 w7 w8"                            # 컷 문장도 원문 보존
    assert doc["cuts"][0]["edit_at"] == 4.0 and doc["cuts"][0]["segment_idx"] == 2
    ch = doc["chapters"][0]
    assert ch["level"] == 1 and ch["t"]["orig"] == [0.0, 11.9] and ch["thumb"] == "thumbs/ch01.jpg"
    assert ch["children"][1]["level"] == 2 and ch["children"][1]["t"]["edit"] == [4.0, 8.0]
    assert doc["notes"]["commands"][0]["t"]["orig"][0] == 8.0
    assert doc["notes"]["links"][0]["label"] == "x"


def test_build_lecture_rejects_bad_outline(tmp_path):
    b = _build(tmp_path)
    bad = {"chapters": [{"id": "1", "title": "A", "summary": "s", "segments": [1, 99], "children": []}]}
    try:
        build_lecture(b, bad, NOTES, INFO, edited_duration=8.1)
    except ValueError as exc:
        assert "chapters[0].segments" in str(exc)
    else:
        raise AssertionError("expected ValueError")


GLOSSARY = [{"term": "REPL", "definition": "입력한 코드를 즉시 실행해 결과를 보여주는 대화형 환경.",
             "analogy": "계산기처럼 한 줄 넣으면 바로 답이 나오는 창구.", "segment_idx": 3},
            {"term": "IDE", "definition": "편집·실행·디버깅을 한곳에서 하는 통합 개발 환경.", "segment_idx": 1}]


def test_glossary_is_optional_and_absent_by_default(tmp_path):
    doc = build_lecture(_build(tmp_path), OUTLINE, NOTES, INFO, edited_duration=8.1)
    assert "glossary" not in doc                      # 구버전 산출물과 동일한 모양
    assert validate_lecture(doc) == []


def test_glossary_entries_get_timeline_pairs_and_validate(tmp_path):
    doc = build_lecture(_build(tmp_path), OUTLINE, NOTES, INFO, edited_duration=8.1, glossary=GLOSSARY)
    assert validate_lecture(doc) == []
    g = doc["glossary"]
    assert [x["term"] for x in g] == ["REPL", "IDE"]
    assert g[0]["t"]["orig"] == [8.0, 11.9] and g[0]["t"]["edit"] == [4.1, 8.0]   # 3번 문장 시각
    assert g[0]["analogy"].startswith("계산기")
    assert "analogy" not in g[1]                      # 비유가 없으면 키 자체를 넣지 않는다


def test_validator_rejects_broken_glossary(tmp_path):
    doc = build_lecture(_build(tmp_path), OUTLINE, NOTES, INFO, edited_duration=8.1, glossary=GLOSSARY)
    doc["glossary"][0]["segment_idx"] = 99
    assert any("glossary[0].segment_idx" in e for e in validate_lecture(doc))
    doc["glossary"][0]["segment_idx"] = 3
    doc["glossary"][1]["term"] = "  "
    assert any("glossary[1].term" in e for e in validate_lecture(doc))


# ── new_lecture_id: 사람이 강의 번호를 주지 않는다 ─────────────────────────────
from datetime import datetime, timedelta, timezone
from lecture_pipeline.assemble import new_lecture_id

KST = timezone(timedelta(hours=9))
AT = datetime(2026, 8, 23, 16, 52, tzinfo=KST)

def test_lecture_id_is_video_id_plus_run_time():
    assert new_lecture_id({"id": "YO4BXrbSgpw"}, AT) == "YO4BXrbSgpw-0823-1652"

def test_same_video_run_twice_gets_different_ids_so_the_viewer_accumulates():
    later = AT + timedelta(minutes=1)
    assert new_lecture_id(INFO, AT) != new_lecture_id(INFO, later)

def test_lecture_id_falls_back_when_info_has_no_video_id():
    assert new_lecture_id({}, AT) == "lecture-0823-1652"

def test_lecture_id_strips_characters_the_viewer_rejects():
    # 뷰어 LID_PATTERN = ^[A-Za-z0-9_-]{1,32}$ — 슬래시·콜론이 섞이면 업로드가 404 로 끊긴다.
    assert new_lecture_id({"id": "https://youtu.be/abc"}, AT) == "httpsyoutubeabc-0823-1652"

def test_lecture_id_stays_within_the_viewer_length_limit():
    assert len(new_lecture_id({"id": "x" * 60}, AT)) <= 32

def test_build_lecture_generates_an_id_when_none_is_given(tmp_path):
    doc = build_lecture(_build(tmp_path), OUTLINE, NOTES, INFO, edited_duration=8.1)
    assert doc["lecture"]["id"].startswith("vid-")
    assert doc["files"] == {"original": "original.mp4", "edited": "edited.mp4", "thumbs_dir": "thumbs/"}


# ── mode: text vs video (Task 4) ────────────────────────────────────────────


def test_text_mode_builds_a_lecture_without_video(tmp_path):
    b = _build(tmp_path)                                   # 기존 헬퍼. cuts.json 은 [] 로 만든다
    (b / "cuts.json").write_text("[]", encoding="utf-8")
    doc = build_lecture(b, OUTLINE, NOTES, INFO, None, "v-0927-1200", mode="text")
    assert doc["schema_version"] == "1.1" and doc["lecture"]["mode"] == "text"
    assert "files" not in doc
    assert doc["lecture"]["duration"]["edit"] == doc["lecture"]["duration"]["orig"]
    assert doc["lecture"]["pipeline"]["policy"] == "corrections_only_v1"
    assert all("thumb" not in ch for ch in doc["chapters"])
    assert validate_lecture(doc) == []


def test_video_mode_keeps_files_thumbs_and_policy(tmp_path):
    b = _build(tmp_path)
    doc = build_lecture(b, OUTLINE, NOTES, INFO, 12.0, "v-0927-1200", mode="video")
    assert doc["lecture"]["mode"] == "video" and doc["files"]["edited"] == "edited.mp4"
    assert doc["chapters"][0]["thumb"] == "thumbs/ch01.jpg"
    assert doc["lecture"]["pipeline"]["policy"] == "speech_only_v1"
    assert validate_lecture(doc) == []


def test_text_mode_cli_never_calls_ffmpeg(tmp_path, monkeypatch):
    from lecture_pipeline import assemble, thumbs
    b = _build(tmp_path)
    (b / "cuts.json").write_text("[]", encoding="utf-8")
    for name, obj in (("outline.json", OUTLINE), ("notes.json", NOTES), ("info.json", INFO)):
        (tmp_path / name).write_text(json.dumps(obj), encoding="utf-8")
    boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError("ffmpeg called"))
    monkeypatch.setattr(assemble.subprocess, "check_output", boom)
    monkeypatch.setattr(thumbs, "grab", boom)
    monkeypatch.setattr("sys.argv", ["lp assemble", "--mode", "text", "--build", str(b), "--outline", str(tmp_path / "outline.json"),
                                     "--notes", str(tmp_path / "notes.json"), "--info", str(tmp_path / "info.json"), "--out", str(tmp_path / "out")])
    assemble.main()
    assert json.loads((tmp_path / "out/lecture.json").read_text())["lecture"]["mode"] == "text"


def test_video_mode_cli_requires_the_video_files(tmp_path, monkeypatch):
    from lecture_pipeline import assemble
    monkeypatch.setattr("sys.argv", ["lp assemble", "--mode", "video", "--build", "b", "--outline", "o", "--notes", "n", "--info", "i", "--out", "x"])
    with pytest.raises(SystemExit):
        assemble.main()


def test_text_mode_edit_equals_orig_exactly_even_past_3_decimals(tmp_path):
    """R1: 텍스트 모드는 map_span 을 타지 않는다 — 컷이 없어도 map_span 은 3자리로 반올림하므로
    orig 가 소수 4자리 이상이면 edit != orig 가 될 수 있다. 그 경로 자체를 피해야 한다."""
    b = _build(tmp_path)
    (b / "cuts.json").write_text("[]", encoding="utf-8")
    sents = json.loads((b / "sentences.json").read_text(encoding="utf-8"))
    sents[0]["start"] = 0.12345
    sents[0]["end"] = 3.98765
    (b / "sentences.json").write_text(json.dumps(sents), encoding="utf-8")
    doc = build_lecture(b, OUTLINE, NOTES, INFO, None, "v-0927-1200", mode="text")
    assert doc["segments"][0]["t"]["orig"] == [0.12345, 3.98765]
    assert doc["segments"][0]["t"]["edit"] == doc["segments"][0]["t"]["orig"]
    assert validate_lecture(doc) == []


@pytest.mark.parametrize("extra", [["--original", "o.mp4", "--edited", "e.mp4"], ["--original", "o.mp4"], ["--edited", "e.mp4"]])
@pytest.mark.parametrize("mode_args", [[], ["--mode", "text"]])
def test_text_mode_refuses_video_files_instead_of_silently_dropping_them(tmp_path, monkeypatch, capsys, extra, mode_args):
    """--original/--edited 를 넘겼는데 --mode video 를 빠뜨리면 텍스트 강의가 조용히 나오던 경로 — 이제 실패한다."""
    from lecture_pipeline import assemble
    monkeypatch.setattr("sys.argv", ["lp assemble", *mode_args, "--build", "b", "--outline", "o", "--notes", "n",
                                     "--info", "i", "--out", str(tmp_path / "out"), *extra])
    with pytest.raises(SystemExit) as e:
        assemble.main()
    assert e.value.code == 2
    assert "--mode video" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
