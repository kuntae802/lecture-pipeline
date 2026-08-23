import json

from lecture_pipeline.adapters import parse_json3, parse_whisper


def test_json3_drops_dummy_events_and_derives_end_times(tmp_path):
    data = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 12000},  # 더미(segs 없음)
            {
                "tStartMs": 160,
                "dDurationMs": 4520,
                "segs": [{"utf8": "안녕하세요."}, {"utf8": " 바이브코딩", "tOffsetMs": 600}, {"utf8": " 대학", "tOffsetMs": 1120}],
            },
            {"tStartMs": 2430, "dDurationMs": 2250, "segs": [{"utf8": "\n"}]},  # 줄바꿈 더미
            {"tStartMs": 9000, "dDurationMs": 1000, "segs": [{"utf8": "[콧방귀]"}, {"utf8": " 네.", "tOffsetMs": 500}]},
        ]
    }
    p = tmp_path / "a.json3"
    p.write_text(json.dumps(data), encoding="utf-8")

    words = parse_json3(p)

    assert [w["text"] for w in words] == ["안녕하세요.", "바이브코딩", "대학", "콧방귀", "네."]
    assert words[0]["start"] == 0.16 and words[0]["end"] == 0.76          # 끝 = 다음 단어 시작
    assert words[1]["start"] == 0.76 and words[1]["end"] == 1.28
    assert words[2]["end"] == 2.78                                          # 다음 단어(9.0)가 멀어 상한(1.5s) 적용
    assert words[3]["type"] == "audio_event" and words[4]["type"] == "word"
    assert words[4]["end"] == 10.0                                          # 마지막 단어: 이벤트 끝


def test_whisper_strips_leading_space_and_keeps_times(tmp_path):
    data = {
        "text": " 안녕하세요 바이브코딩",
        "segments": [
            {"start": 0.0, "end": 1.5, "text": " 안녕하세요 바이브코딩",
             "words": [{"word": " 안녕하세요", "start": 0.1, "end": 0.8}, {"word": " 바이브코딩", "start": 0.9, "end": 0.9}]},
        ],
    }
    p = tmp_path / "w.json"
    p.write_text(json.dumps(data), encoding="utf-8")

    words = parse_whisper(p)

    assert [w["text"] for w in words] == ["안녕하세요", "바이브코딩"]
    assert words[0] == {"start": 0.1, "end": 0.8, "text": "안녕하세요", "type": "word"}
    assert words[1]["end"] > words[1]["start"]  # 0길이 단어 보정
