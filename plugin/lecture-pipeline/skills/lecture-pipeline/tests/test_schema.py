import json

from lecture_pipeline.schema import MINIMAL_EXAMPLE, validate_lecture


def test_minimal_example_is_valid():
    assert validate_lecture(MINIMAL_EXAMPLE) == []


def test_missing_edit_inside_cut_is_reported():
    doc = json.loads(json.dumps(MINIMAL_EXAMPLE))
    doc["segments"][0]["t"]["edit"] = [9999, 10000]   # 컷 안인데 edit 있음
    doc["cuts"] = [{"id": 1, "orig": [0.0, 5.0], "edit_at": 0.0, "category": "misstatement",
                    "confidence": "high", "removed_text": "x", "note": "n", "segment_idx": 1}]
    errs = validate_lecture(doc)
    assert any("segments[0]" in e and "edit" in e for e in errs)


def test_bad_category_and_schema_version():
    doc = json.loads(json.dumps(MINIMAL_EXAMPLE))
    doc["schema_version"] = "0.9"
    doc["cuts"] = [{"id": 1, "orig": [1.0, 2.0], "edit_at": 1.0, "category": "filler",
                    "confidence": "high", "removed_text": "x", "note": "n", "segment_idx": 1}]
    errs = validate_lecture(doc)
    assert any("schema_version" in e for e in errs)
    assert any("category" in e for e in errs)


def test_overlapping_cuts_and_chapter_range():
    doc = json.loads(json.dumps(MINIMAL_EXAMPLE))
    doc["cuts"] = [{"id": 1, "orig": [3.0, 6.0], "edit_at": 3.0, "category": "duplicate", "confidence": "high", "removed_text": "x", "note": "n", "segment_idx": None},
                   {"id": 2, "orig": [5.0, 7.0], "edit_at": 5.0, "category": "duplicate", "confidence": "high", "removed_text": "y", "note": "n", "segment_idx": None}]
    doc["chapters"][0]["segments"] = [1, 99]
    errs = validate_lecture(doc)
    assert any("overlap" in e for e in errs)
    assert any("chapters[0].segments" in e for e in errs)


import copy
from lecture_pipeline.schema import MINIMAL_EXAMPLE, MINIMAL_TEXT_EXAMPLE, MODES, SCHEMA_VERSIONS, doc_mode, load_schema, validate_lecture


def test_text_example_is_valid_and_has_no_files():
    assert validate_lecture(MINIMAL_TEXT_EXAMPLE) == []
    assert "files" not in MINIMAL_TEXT_EXAMPLE
    assert doc_mode(MINIMAL_TEXT_EXAMPLE) == "text"


def test_old_video_example_still_valid_and_defaults_to_video():
    assert validate_lecture(MINIMAL_EXAMPLE) == []
    assert doc_mode(MINIMAL_EXAMPLE) == "video"


def test_unknown_mode_is_rejected():
    d = copy.deepcopy(MINIMAL_TEXT_EXAMPLE)
    d["lecture"]["mode"] = "audio"
    assert any("lecture.mode" in e for e in validate_lecture(d))


def test_text_mode_requires_version_1_1():
    d = copy.deepcopy(MINIMAL_TEXT_EXAMPLE)
    d["schema_version"] = "1.0"
    assert any("1.1" in e for e in validate_lecture(d))


def test_video_mode_still_requires_files():
    d = copy.deepcopy(MINIMAL_EXAMPLE)
    del d["files"]
    assert any("files" in e for e in validate_lecture(d))


def test_text_mode_rejects_cuts_and_edit_drift():
    d = copy.deepcopy(MINIMAL_TEXT_EXAMPLE)
    d["cuts"] = [{"id": 1, "orig": [0.5, 1.5], "edit_at": 0.5, "category": "duplicate", "confidence": "high", "removed_text": "x", "note": ""}]
    assert any("text mode" in e and "cuts" in e for e in validate_lecture(d))
    d = copy.deepcopy(MINIMAL_TEXT_EXAMPLE)
    d["lecture"]["duration"]["edit"] = 9.0
    assert any("duration.edit" in e for e in validate_lecture(d))
    d = copy.deepcopy(MINIMAL_TEXT_EXAMPLE)
    d["segments"][0]["t"]["edit"] = [0.0, 1.9]
    assert any("edit must equal orig" in e for e in validate_lecture(d))


def test_text_mode_rejects_chapter_thumbs():
    d = copy.deepcopy(MINIMAL_TEXT_EXAMPLE)
    d["chapters"][0]["thumb"] = "thumbs/ch01.jpg"
    assert any("thumb" in e for e in validate_lecture(d))


def test_json_schema_matches_python_constants():
    s = load_schema()
    assert set(s["properties"]["schema_version"]["enum"]) == set(SCHEMA_VERSIONS)
    assert tuple(s["properties"]["lecture"]["properties"]["mode"]["enum"]) == MODES
    assert "files" not in s["required"]
