import json

from lecture_pipeline.merge_edits import merge


def _words(n):
    # 단어 하나 = 0.5초 → 한 단어 컷(0.5s)은 MIN_CUT_SEC(0.8s) 미만으로 거부돼야 한다
    return [{"start": i * 1.0, "end": i * 1.0 + 0.5, "text": f"w{i+1}", "type": "word"} for i in range(n)]


MANIFEST = [{"n": 1, "file": "01.md", "word_from": 1, "word_to": 20, "ctx_word_from": 1, "start": 0, "end": 20},
            {"n": 2, "file": "02.md", "word_from": 21, "word_to": 40, "ctx_word_from": 19, "start": 20, "end": 40}]


def _setup(tmp_path, cuts_by_chunk, manifest=MANIFEST):
    b = tmp_path / "build"; c = tmp_path / "chunks"; b.mkdir(); c.mkdir()
    (b / "words.json").write_text(json.dumps({"source": "youtube_json3", "words": _words(40)}), encoding="utf-8")
    (c / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for n, cuts in cuts_by_chunk.items():
        (c / f"{n:02d}.cuts.json").write_text(json.dumps(cuts), encoding="utf-8")
        (c / f"{n:02d}.corrections.json").write_text(json.dumps([{"idx": 3, "from": "w3", "to": "W3"}]), encoding="utf-8")
    return b, c


def test_merge_sorts_and_computes_spans(tmp_path):
    b, c = _setup(tmp_path, {2: [{"from_idx": 30, "to_idx": 32, "category": "duplicate", "confidence": "medium", "note": "n"}],
                             1: [{"from_idx": 5, "to_idx": 7, "category": "misstatement", "confidence": "high", "note": "n"}]})
    cuts, corr, errs = merge(b, c)
    assert errs == []
    assert [x["id"] for x in cuts] == [1, 2]
    assert cuts[0]["orig"] == [4.0, 6.5] and cuts[0]["removed_text"] == "w5 w6 w7"
    assert cuts[0]["from_idx"] == 5 and cuts[0]["to_idx"] == 7
    assert corr == [{"idx": 3, "from": "w3", "to": "W3"}]


def test_merge_rejects_context_cut_tiny_cut_and_overlap(tmp_path):
    b, c = _setup(tmp_path, {1: [],
                             2: [{"from_idx": 19, "to_idx": 22, "category": "duplicate", "confidence": "high", "note": ""},
                                 {"from_idx": 25, "to_idx": 25, "category": "duplicate", "confidence": "high", "note": ""},
                                 {"from_idx": 30, "to_idx": 33, "category": "duplicate", "confidence": "high", "note": ""},
                                 {"from_idx": 32, "to_idx": 35, "category": "duplicate", "confidence": "high", "note": ""}]})
    _, _, errs = merge(b, c)
    assert any("context" in e for e in errs)
    assert any("too short" in e for e in errs)
    assert any("overlap" in e for e in errs)


def test_merge_reports_missing_chunk_file_and_bad_category(tmp_path):
    b, c = _setup(tmp_path, {1: [{"from_idx": 2, "to_idx": 4, "category": "filler", "confidence": "high", "note": ""}]})
    _, _, errs = merge(b, c)
    assert any("chunk 02" in e and "missing" in e for e in errs)
    assert any("category" in e for e in errs)
