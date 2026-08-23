"""YouTube 자동자막 json3 → words 스트림.

json3 구조(실측, 1강 기준):
- events[]: {tStartMs, dDurationMs, segs[]} — 절반은 segs == [{"utf8": "\n"}] 인 줄바꿈 더미
- segs[]: {utf8, tOffsetMs?} — 단어 시작 오프셋만 있고 끝 시각은 없음(첫 seg는 tOffsetMs 없음 = 0)
- 오디오 이벤트는 "[콧방귀]" 처럼 대괄호 텍스트로 단어 사이에 섞여 나옴
- 중복(굴림 반복)은 VTT 렌더링 산물이며 json3 자체엔 없음 — 그래도 preprocess 단계의 가드가 한 번 더 본다
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_AUDIO_EVENT = re.compile(r"^\[[^\]]+\]$")
# 끝 시각이 없을 때 단어 하나에 부여하는 상한(초). 다음 단어가 이보다 늦으면 멈춤으로 본다.
MAX_WORD_DUR = 1.5


def _events_to_raw(events: list[dict]) -> list[tuple[float, float, str]]:
    """(단어 시작, 소속 이벤트 끝, 텍스트) 평탄화. 더미·공백 seg 제거."""
    raw: list[tuple[float, float, str]] = []
    for e in events:
        segs = e.get("segs")
        if not segs:
            continue
        t0 = e.get("tStartMs", 0)
        ev_end = t0 + e.get("dDurationMs", 0)
        for s in segs:
            text = s.get("utf8", "").strip()
            if not text:
                continue
            start = t0 + s.get("tOffsetMs", 0)
            raw.append((start / 1000.0, ev_end / 1000.0, text))
    return raw


def parse_json3(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = _events_to_raw(data.get("events", []))
    words: list[dict] = []
    for i, (start, ev_end, text) in enumerate(raw):
        nxt = raw[i + 1][0] if i + 1 < len(raw) else None
        # 끝 = 다음 단어 시작 / 이벤트 끝 / 상한 중 가장 이른 것 (단 시작보다는 뒤)
        cands = [ev_end, start + MAX_WORD_DUR]
        if nxt is not None:
            cands.append(nxt)
        end = min(c for c in cands if c > start) if any(c > start for c in cands) else start + 0.2
        kind = "audio_event" if _AUDIO_EVENT.match(text) else "word"
        if kind == "audio_event":
            text = text[1:-1]
        words.append({"start": round(start, 3), "end": round(end, 3), "text": text, "type": kind})
    return words
