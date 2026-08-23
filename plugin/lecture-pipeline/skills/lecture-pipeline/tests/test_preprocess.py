from lecture_pipeline.preprocess import build_sentences, dedup_overlap_guard, render_indexed


def W(start, end, text, kind="word"):
    return {"start": start, "end": end, "text": text, "type": kind}


def test_dedup_guard_removes_rolling_repeat_but_keeps_real_repetition():
    words = [W(0.0, 0.3, "레버리지라고"), W(0.3, 0.6, "하는"), W(0.6, 0.9, "부제를"),
             # 굴림 잔재: 직전 3단어가 0.01초 뒤 그대로 다시 나옴
             W(0.91, 0.92, "레버리지라고"), W(0.92, 0.93, "하는"), W(0.93, 0.94, "부제를"),
             W(1.0, 1.3, "통해서"),
             # 진짜 반복(수 분 뒤 같은 어구) — 시간 조건 때문에 보존
             W(300.0, 300.3, "레버리지라고"), W(300.3, 300.6, "하는"), W(300.6, 300.9, "부제를")]
    out, removed = dedup_overlap_guard(words)
    assert removed == 3
    assert [w["text"] for w in out] == ["레버리지라고", "하는", "부제를", "통해서", "레버리지라고", "하는", "부제를"]


def test_sentences_split_on_punctuation_gap_and_skip_audio_events():
    words = [W(0.0, 0.3, "안녕하세요."), W(0.4, 0.6, "오늘은"), W(0.6, 0.9, "레버리지"),
             W(1.0, 1.2, "콧방귀", "audio_event"),
             W(1.3, 1.6, "얘기예요"),          # 구두점 없음 → 다음 단어까지 2.5초 멈춤으로 끊김
             W(4.1, 4.4, "자"), W(4.4, 4.8, "시작합니다?")]
    sents = build_sentences(words)
    assert [s["text"] for s in sents] == ["안녕하세요.", "오늘은 레버리지 얘기예요", "자 시작합니다?"]
    assert sents[1]["start"] == 0.4 and sents[1]["end"] == 1.6
    assert (sents[1]["word_from"], sents[1]["word_to"]) == (2, 4)   # audio_event 는 번호를 먹지 않음
    assert sents[2]["idx"] == 3


def test_render_indexed_marks_silence_and_audio_events():
    words = [W(0.0, 0.3, "안녕하세요."), W(1.0, 1.2, "콧방귀", "audio_event"), W(1.5, 1.8, "네.")]
    md = render_indexed(words, "t")
    lines = md.splitlines()
    assert lines[5].startswith("[    1] [   0.000-   0.300] 안녕하세요.")
    assert "_(audio event @ 1.00: 콧방귀)_" in lines[6]
    assert "_(silence 1.20s)_" in lines[7]
    assert lines[8].startswith("[    2]")


def test_has_punctuation_distinguishes_the_two_caption_styles():
    from lecture_pipeline.preprocess import has_punctuation
    with_punct = [W(i, i + 0.5, "가나." if i % 5 == 0 else "다라") for i in range(50)]
    without = [W(i, i + 0.5, "다라") for i in range(50)]
    assert has_punctuation(with_punct) is True
    assert has_punctuation(without) is False
    assert has_punctuation([]) is False


def test_sentences_fall_back_to_pauses_when_captions_have_no_punctuation():
    # 구두점이 없는 자동자막(실제로 존재한다) — 2초 기준이면 한 덩어리가 되므로 0.7초 멈춤으로 끊는다
    words = [W(0.0, 0.4, "우리"), W(0.4, 0.9, "오늘은"), W(0.9, 1.3, "파이썬을"),
             W(2.2, 2.6, "배웁니다"),            # 0.9초 멈춤 → 경계
             W(2.7, 3.1, "먼저"), W(3.1, 3.5, "설치부터")]
    sents = build_sentences(words)
    assert [s["text"] for s in sents] == ["우리 오늘은 파이썬을", "배웁니다 먼저 설치부터"]


def test_pause_mode_caps_sentence_length_more_tightly():
    words = [W(i * 0.3, i * 0.3 + 0.25, "단어") for i in range(60)]   # 멈춤 없이 60단어
    sents = build_sentences(words)
    assert max(len(s["text"].split()) for s in sents) <= 25          # 구두점 모드였다면 60까지 갔다
    assert len(sents) == 3
