from lecture_pipeline.chunk import plan_chunks, slice_indexed


def S(idx, start, end, wf, wt):
    return {"idx": idx, "start": start, "end": end, "text": f"s{idx}", "word_from": wf, "word_to": wt}


def test_plan_chunks_cuts_at_sentence_boundaries_near_target():
    sents = [S(i + 1, i * 100.0, i * 100.0 + 90, i * 10 + 1, i * 10 + 10) for i in range(20)]  # 20문장 × 100초
    chunks = plan_chunks(sents, target_sec=660, max_sec=780)
    assert chunks[0]["word_from"] == 1 and chunks[-1]["word_to"] == 200
    assert chunks[0]["n"] == 1 and chunks[0]["file"] == "01.md"
    for a, b in zip(chunks, chunks[1:]):
        assert b["word_from"] == a["word_to"] + 1          # 빈틈·겹침 없음
        assert a["end"] - a["start"] <= 780
    assert all(c["ctx_word_from"] <= c["word_from"] for c in chunks)
    assert chunks[1]["ctx_word_from"] == chunks[1]["word_from"] - 20   # 앞 2문장(각 10단어)이 문맥


def test_slice_indexed_keeps_only_window_and_marks_context():
    md = "\n".join(["# h", "", "[    1] [   0.000-   0.500] 가", "  _(silence 0.70s)_",
                    "[    2] [   1.200-   1.500] 나", "[    3] [   1.500-   1.900] 다", "[    4] [   2.000-   2.300] 라",
                    "[    5] [   2.400-   2.800] 마"])
    body = slice_indexed(md, ctx_from=1, word_from=3, word_to=4)
    assert "[    1]" in body and "CONTEXT" in body.split("[    3]")[0]   # 문맥 표시 후 편집 구간
    assert "EDITABLE" in body and "[    5]" not in body
    assert body.strip().endswith("라")


def test_short_tail_chunk_is_absorbed_into_the_previous_one():
    # 마지막 문장이 경계 직후에 시작해 단어 몇 개짜리 청크가 생기는 실제 사례(22분 영상에서 1단어 청크 발생)
    sents = [S(i + 1, i * 100.0, i * 100.0 + 90, i * 10 + 1, i * 10 + 10) for i in range(7)]
    sents.append(S(8, 700.0, 701.5, 71, 71))          # 경계 직후에 시작하는 1.5초·1단어 꼬리
    chunks = plan_chunks(sents, target_sec=660, max_sec=780)
    assert len(chunks) == 1                            # 별도 청크로 남지 않는다
    assert chunks[-1]["word_to"] == 71 and chunks[-1]["end"] == 701.5


def test_long_tail_chunk_is_kept_separate():
    sents = [S(i + 1, i * 100.0, i * 100.0 + 90, i * 10 + 1, i * 10 + 10) for i in range(10)]
    chunks = plan_chunks(sents, target_sec=660, max_sec=780)
    assert len(chunks) == 2 and chunks[-1]["end"] - chunks[-1]["start"] >= 90
