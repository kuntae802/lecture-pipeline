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


def _setup_no_cuts(tmp_path, n_chunks):
    b = tmp_path / "build"; c = tmp_path / "chunks"; b.mkdir(); c.mkdir()
    (b / "words.json").write_text(json.dumps({"source": "youtube_json3", "words": _words(n_chunks * 20)}), encoding="utf-8")
    manifest = [{"n": i, "file": f"{i:02d}.md", "word_from": (i - 1) * 20 + 1, "word_to": i * 20,
                 "ctx_word_from": (i - 1) * 20 + 1, "start": (i - 1) * 20, "end": i * 20}
                for i in range(1, n_chunks + 1)]
    (c / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return b, c


def test_no_cuts_mode_needs_only_corrections(tmp_path):
    build, chunks = _setup_no_cuts(tmp_path, n_chunks=2)          # 기존 헬퍼
    for n in (1, 2):
        (chunks / f"{n:02d}.corrections.json").write_text("[]", encoding="utf-8")
    cuts, corr, errs = merge(build, chunks, no_cuts=True)
    assert errs == [] and cuts == []


def test_no_cuts_mode_rejects_a_missing_corrections_file(tmp_path):
    build, chunks = _setup_no_cuts(tmp_path, n_chunks=2)
    (chunks / "01.corrections.json").write_text("[]", encoding="utf-8")
    _, _, errs = merge(build, chunks, no_cuts=True)
    assert errs == ["chunk 02: corrections file missing"]


def test_no_cuts_mode_ignores_stray_cut_files(tmp_path):
    build, chunks = _setup_no_cuts(tmp_path, n_chunks=1)
    (chunks / "01.corrections.json").write_text("[]", encoding="utf-8")
    (chunks / "01.cuts.json").write_text('[{"from_idx": 1, "to_idx": 3, "category": "duplicate"}]', encoding="utf-8")
    cuts, _, errs = merge(build, chunks, no_cuts=True)
    assert errs == [] and cuts == []


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


# ── 교정 반영 문장(sentences.corrected.json) ─────────────────────────────────
# 구조화·용어집 패스가 교정 전 문장을 읽으면 잘못 인식된 용어가 목차 제목과 용어집에 그대로 들어간다
# (2026-09-28 e2e 에서 확인). 병합이 교정을 반영한 문장 파일을 따로 써서 그 패스들이 읽게 한다.
from lecture_pipeline.merge_edits import corrected_sentences, main as merge_main

SENTS = [{"idx": 1, "start": 0.0, "end": 2.5, "text": "w1 w2 w3", "word_from": 1, "word_to": 3},
         {"idx": 2, "start": 3.0, "end": 4.5, "text": "w4 w5", "word_from": 4, "word_to": 5}]


def test_corrected_sentences_apply_corrections_and_keep_everything_else():
    words = {i: {"text": f"w{i}"} for i in range(1, 6)}
    out = corrected_sentences(SENTS, words, [{"idx": 2, "from": "w2", "to": "파이썬"}, {"idx": 5, "from": "w5", "to": "VS Code"}])
    assert [s["text"] for s in out] == ["w1 파이썬 w3", "w4 VS Code"]
    assert [{k: v for k, v in s.items() if k != "text"} for s in out] == [{k: v for k, v in s.items() if k != "text"} for s in SENTS]
    assert SENTS[0]["text"] == "w1 w2 w3"          # 입력을 바꾸지 않는다


def test_merge_cli_writes_corrected_sentences_and_leaves_the_original(tmp_path, monkeypatch):
    build, chunks = _setup_no_cuts(tmp_path, n_chunks=1)
    sents = [{"idx": 1, "start": 0.0, "end": 19.5, "text": " ".join(f"w{i}" for i in range(1, 21)), "word_from": 1, "word_to": 20}]
    (build / "sentences.json").write_text(json.dumps(sents), encoding="utf-8")
    (chunks / "01.corrections.json").write_text(json.dumps([{"idx": 3, "from": "w3", "to": "W3"}]), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["lp merge", "--build", str(build), "--chunks", str(chunks), "--no-cuts"])
    merge_main()
    fixed = json.loads((build / "sentences.corrected.json").read_text(encoding="utf-8"))
    assert fixed[0]["text"].split()[2] == "W3"
    assert json.loads((build / "sentences.json").read_text(encoding="utf-8")) == sents
    merge_main()                                    # 다시 돌려도 같은 결과(원본에서 매번 새로 만든다)
    assert json.loads((build / "sentences.corrected.json").read_text(encoding="utf-8")) == fixed


def test_merge_cli_writes_nothing_when_sentences_are_missing(tmp_path, monkeypatch):
    build, chunks = _setup_no_cuts(tmp_path, n_chunks=1)
    (chunks / "01.corrections.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["lp merge", "--build", str(build), "--chunks", str(chunks), "--no-cuts"])
    import pytest
    with pytest.raises(FileNotFoundError):
        merge_main()
    assert not (build / "cuts.json").exists() and not (build / "corrections.json").exists()
