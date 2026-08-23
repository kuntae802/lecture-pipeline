"""openai-whisper `--output_format json --word_timestamps True` 산출물 → words 스트림.

구조: {"text", "segments": [{"start", "end", "text", "words": [{"word", "start", "end", "probability"}]}], "language"}
- word 텍스트는 선행 공백을 달고 옴(" 안녕하세요") → strip
- 오디오 이벤트 태깅은 없음(전부 word)
"""
from __future__ import annotations

import json
from pathlib import Path


def parse_whisper(path: str | Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    words: list[dict] = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            text = (w.get("word") or "").strip()
            if not text:
                continue
            start = float(w["start"])
            end = float(w["end"])
            if end <= start:
                end = start + 0.05
            words.append({"start": round(start, 3), "end": round(end, 3), "text": text, "type": "word"})
    return words
