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
