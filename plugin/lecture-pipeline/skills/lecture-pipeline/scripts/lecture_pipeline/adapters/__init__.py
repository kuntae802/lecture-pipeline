"""전사 소스 어댑터 — 각 소스를 공통 words 스트림으로 바꾼다.

공통 word 레코드(video-use `words` JSON과 호환):
    {"start": float(초), "end": float(초), "text": str, "type": "word" | "audio_event"}
"""
from .youtube_json3 import parse_json3
from .whisper_json import parse_whisper

ADAPTERS = {
    "youtube_json3": parse_json3,
    "whisper": parse_whisper,
}

__all__ = ["ADAPTERS", "parse_json3", "parse_whisper"]
