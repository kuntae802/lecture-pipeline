"""전처리: words 스트림 → (겹침 가드) → 문장 조립 → 산출물 3종.

산출물(out_dir):
- words.json      : {"source", "words": [...]}  — video-use `words` 호환
- sentences.json  : [{"idx", "start", "end", "text", "word_from", "word_to"}]  (word 번호는 1-based, audio_event 제외)
- indexed.md      : LLM 정제 입력. video-use index_transcript.py 와 같은 형식
                    `[   N] [ start- end] 텍스트`, 0.5초 이상 멈춤은 `_(silence Xs)_`, 오디오 이벤트는 이탤릭 한 줄

사용:
    python3 <스킬>/scripts/lp.py preprocess --source youtube_json3 --input 01.ko.json3 --out build/01/youtube
    python3 <스킬>/scripts/lp.py preprocess --source whisper --input 01.json --out build/01/whisper
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .adapters import ADAPTERS

SENT_END = re.compile(r"[.?!][\"'”’)\]]*$")
# 구두점이 있는 자막(예: 마침표 2,271개)과 아예 없는 자막이 둘 다 존재한다 — 모드를 나눠 잡는다.
SENT_GAP_SEC = 2.0      # 구두점 모드: 이 이상 멈추면 구두점이 없어도 끊는다
SENT_MAX_WORDS = 60     # 구두점 모드 안전장치
PAUSE_GAP_SEC = 0.7     # 구두점 없음 모드: 짧은 숨도 경계로 본다
PAUSE_MAX_WORDS = 25    # 구두점 없음 모드 안전장치
PUNCT_MIN_RATIO = 0.01  # 단어 100개당 1개 이상 문장부호로 끝나면 "구두점 있는 전사" 로 본다
SILENCE_MARK_SEC = 0.5  # indexed.md 에 멈춤을 표시하는 최소 길이


def dedup_overlap_guard(words: list[dict], min_k: int = 3, max_k: int = 12) -> tuple[list[dict], int]:
    """굴림(rolling) 자막 잔재 가드 — 직전 단어열의 꼬리 k개가 바로 이어서 다시 나오면 뒤쪽을 버린다.

    json3 는 실측 0건이지만 VTT 경로·다른 강의에서 나올 수 있어 같은 자리에 둔다.
    시간도 같이 본다: 반복 후보의 시작이 원본 단어 시작보다 뒤이면서 2초 이내일 때만 중복으로 본다.
    반환: (정리된 words, 제거 개수)
    """
    out: list[dict] = []
    removed = 0
    i = 0
    n = len(words)
    while i < n:
        matched = 0
        for k in range(min(max_k, len(out), n - i), min_k - 1, -1):
            tail = [w["text"] for w in out[-k:]]
            head = [w["text"] for w in words[i : i + k]]
            if tail == head and 0 <= words[i]["start"] - out[-k]["start"] <= 2.0:
                matched = k
                break
        if matched:
            removed += matched
            i += matched
            continue
        out.append(words[i])
        i += 1
    return out, removed


def has_punctuation(words: list[dict]) -> bool:
    """자동자막에 문장부호가 실려 오는지. 없으면 멈춤 기반으로 끊어야 한 덩어리가 되지 않는다."""
    only = [w for w in words if w.get("type", "word") == "word"]
    if not only:
        return False
    ends = sum(1 for w in only if SENT_END.search(w["text"]))
    # 비율로만 판정한다 — 절대 하한을 두면 짧은 입력이 잘못 분류된다.
    # 실측: 구두점 있는 자막은 단어의 9%가 문장부호로 끝났고, 없는 자막은 0% 였다.
    return ends >= 1 and ends / len(only) >= PUNCT_MIN_RATIO


def build_sentences(words: list[dict]) -> list[dict]:
    """문장 조립. 문장부호가 있으면 그것을, 없으면 멈춤을 경계로 쓴다. audio_event 는 문장에 넣지 않는다."""
    punct_mode = has_punctuation(words)
    gap_sec = SENT_GAP_SEC if punct_mode else PAUSE_GAP_SEC
    max_words = SENT_MAX_WORDS if punct_mode else PAUSE_MAX_WORDS
    sents: list[dict] = []
    cur: list[tuple[int, dict]] = []  # (1-based word 번호, word)
    widx = 0

    def flush() -> None:
        if not cur:
            return
        sents.append(
            {
                "idx": len(sents) + 1,
                "start": cur[0][1]["start"],
                "end": cur[-1][1]["end"],
                "text": " ".join(w["text"] for _, w in cur),
                "word_from": cur[0][0],
                "word_to": cur[-1][0],
            }
        )
        cur.clear()

    only_words = [w for w in words if w.get("type", "word") == "word"]
    for j, w in enumerate(only_words):
        widx += 1
        cur.append((widx, w))
        nxt = only_words[j + 1] if j + 1 < len(only_words) else None
        if punct_mode and SENT_END.search(w["text"]):
            flush()
        elif nxt is not None and nxt["start"] - w["end"] >= gap_sec:
            flush()
        elif len(cur) >= max_words:
            flush()
    flush()
    return sents


def render_indexed(words: list[dict], title: str) -> str:
    lines = [
        f"# Indexed transcript: {title}",
        f"# Total entries (raw): {len(words)}",
        "# Format per word: [N] [start-end] text",
        "# (audio events shown in italics for context, not indexed)",
        "",
    ]
    idx = 0
    last_end = None
    for w in words:
        if w.get("type", "word") == "audio_event":
            lines.append(f"  _(audio event @ {w['start']:.2f}: {w['text']})_")
            continue
        idx += 1
        if last_end is not None and w["start"] - last_end > SILENCE_MARK_SEC:
            lines.append(f"  _(silence {w['start'] - last_end:.2f}s)_")
        lines.append(f"[{idx:5d}] [{w['start']:8.3f}-{w['end']:8.3f}] {w['text']}")
        last_end = w["end"]
    return "\n".join(lines) + "\n"


def run(source: str, input_path: Path, out_dir: Path, title: str | None = None, dedup_guard: bool = False) -> dict:
    words = ADAPTERS[source](input_path)
    # 가드는 VTT 굴림 잔재 전용. json3·whisper 는 원천에 중복이 없고(1강 실측 99.9% 일치),
    # 켜면 화자의 진짜 재발화("점 찍고 그다음 하위 정보" 반복 등)를 조용히 지워 컷 리스트에서 사라진다 →
    # 기본 OFF, 재발화 판단은 LLM 정제 패스 몫(감사 가능한 컷으로 남김).
    removed = 0
    if dedup_guard:
        words, removed = dedup_overlap_guard(words)
    sents = build_sentences(words)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "words.json").write_text(
        json.dumps({"source": source, "words": words}, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "sentences.json").write_text(json.dumps(sents, ensure_ascii=False, indent=0), encoding="utf-8")
    (out_dir / "indexed.md").write_text(render_indexed(words, title or input_path.stem), encoding="utf-8")
    n_words = sum(1 for w in words if w.get("type", "word") == "word")
    stats = {
        "source": source,
        "words": n_words,
        "audio_events": len(words) - n_words,
        "dedup_removed": removed,
        "sentences": len(sents),
        "duration_sec": round(words[-1]["end"], 1) if words else 0,
        "avg_sentence_words": round(n_words / max(1, len(sents)), 1),
        "punct_endings": sum(1 for s in sents if SENT_END.search(s["text"])),
        "sentence_mode": "punctuation" if has_punctuation(words) else "pause",
    }
    (out_dir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=sorted(ADAPTERS), required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title")
    ap.add_argument("--dedup-guard", action="store_true", help="VTT 굴림 잔재 가드 켜기(json3·whisper 엔 끄는 게 기본)")
    a = ap.parse_args()
    stats = run(a.source, Path(a.input), Path(a.out), a.title, dedup_guard=a.dedup_guard)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
