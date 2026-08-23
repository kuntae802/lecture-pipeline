"""모든 산출물 → lecture.json (+ 챕터 썸네일). 편집본 시간은 여기서만 계산한다.

입력: build_dir(words.json·sentences.json·cuts.json·corrections.json) · outline.json · notes.json · yt-dlp info.json · 편집본 mp4(ffprobe 길이)
사용:
  python3 <스킬>/scripts/lp.py assemble --build workspace/build/<ID>/youtube --outline workspace/build/<ID>/outline.json \
    --notes workspace/build/<ID>/notes.json --info workspace/raw/<ID>/source.info.json \
    --original workspace/raw/<ID>/source.mp4 --edited workspace/out/<ID>/edited.mp4 --out workspace/out/<ID>
강의 id 는 여기서 `<video_id>-<MMDD-HHMM>` 로 자동 생성한다 — 사람이 번호를 주지 않는다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import thumbs
from .ids import stamped_id
from .schema import validate_lecture
from .timeline import edit_at, map_span

KST = timezone(timedelta(hours=9))


def _word_index(words):
    out, n = {}, 0
    for w in words:
        if w.get("type", "word") == "word":
            n += 1
            out[n] = w
    return out


def _segment_text(sent: dict, widx: dict, cut_words: set[int], corr: dict[int, str]) -> str:
    """문장 텍스트 = 컷된 단어 제외 + 표기 교정 적용. 문장 전체가 컷이면 원문을 그대로 둔다(검토 탭에서 읽을 수 있게)."""
    toks = [corr.get(i, widx[i]["text"]) for i in range(sent["word_from"], sent["word_to"] + 1) if i in widx and i not in cut_words]
    if toks:
        return " ".join(toks)
    return " ".join(corr.get(i, widx[i]["text"]) for i in range(sent["word_from"], sent["word_to"] + 1) if i in widx) or sent["text"]


def _find_segment(t: float, sents: list[dict]) -> int | None:
    for s in sents:
        if s["start"] <= t <= s["end"]:
            return s["idx"]
    return None


def _chapter(ch: dict, sents: list[dict], cuts, thumb_name: str | None) -> dict:
    a, b = int(ch["segments"][0]), int(ch["segments"][1])
    # 범위가 어긋나면 시간 계산용으로만 클램프하고 segments 는 원값을 둬 validate_lecture 가 거부하게 한다
    ca = max(1, min(a, len(sents)))
    cb = max(ca, min(b, len(sents)))
    s0, s1 = sents[ca - 1], sents[cb - 1]
    node = {
        "id": str(ch["id"]), "level": 1 if "." not in str(ch["id"]) else 2,
        "title": ch["title"], "summary": ch.get("summary", ""),
        "t": {"orig": [s0["start"], s1["end"]], "edit": map_span(s0["start"], s1["end"], cuts)},
        "segments": [a, b],
    }
    if thumb_name:
        node["thumb"] = thumb_name
    node["children"] = [_chapter(c, sents, cuts, None) for c in ch.get("children", []) or []]
    return node


def new_lecture_id(info: dict, now: datetime | None = None) -> str:
    """강의 id = `<video_id>-<MMDD-HHMM>`. 사람이 번호를 정하지 않는다(2026-08-23 결정).

    번호를 손으로 주는 방식은 빠뜨렸을 때 조용히 앞 강의를 덮어썼다 — 뷰어 업로드가
    id 하나만 보고 파일·DB 를 통째로 대체하기 때문이다. 조립할 때마다 새 id 가 나오므로
    같은 영상을 다시 돌려도 뷰어 목록에 나란히 쌓인다.
    뷰어의 id 규칙(영숫자·`-`·`_`, 32자 이내)을 넘지 않게 video id 는 20자로 자른다."""
    return stamped_id(info.get("id"), now)


def build_lecture(build_dir: Path, outline: dict, notes: dict, info: dict, edited_duration: float,
                  lecture_id: str | None = None, glossary: list[dict] | None = None) -> dict:
    lecture_id = lecture_id or new_lecture_id(info)
    words = json.loads((build_dir / "words.json").read_text(encoding="utf-8"))["words"]
    sents = json.loads((build_dir / "sentences.json").read_text(encoding="utf-8"))
    cuts_raw = json.loads((build_dir / "cuts.json").read_text(encoding="utf-8"))
    corr_path = build_dir / "corrections.json"
    corr = {c["idx"]: c["to"] for c in json.loads(corr_path.read_text(encoding="utf-8"))} if corr_path.exists() else {}
    widx = _word_index(words)
    cuts = [tuple(c["orig"]) for c in cuts_raw]
    cut_words = {i for c in cuts_raw for i in range(c["from_idx"], c["to_idx"] + 1)}
    total = float(info.get("duration") or (words[-1]["end"] if words else 0))

    segments = [{"idx": s["idx"], "text": _segment_text(s, widx, cut_words, corr),
                 "t": {"orig": [s["start"], s["end"]], "edit": map_span(s["start"], s["end"], cuts)}} for s in sents]
    cuts_out = [{"id": c["id"], "orig": c["orig"], "edit_at": edit_at(c["orig"][0], cuts), "category": c["category"],
                 "confidence": c["confidence"], "removed_text": c["removed_text"], "note": c.get("note", ""),
                 "segment_idx": _find_segment(c["orig"][0], sents)} for c in cuts_raw]
    chapters = [_chapter(ch, sents, cuts, f"thumbs/ch{i:02d}.jpg") for i, ch in enumerate(outline["chapters"], 1)]

    def note_t(n: dict) -> dict:
        s = sents[min(max(int(n["segment_idx"]), 1), len(sents)) - 1]
        return {"orig": [s["start"], s["end"]], "edit": map_span(s["start"], s["end"], cuts)}

    notes_out = {
        "commands": [{"text": n["text"], "segment_idx": int(n["segment_idx"]), "t": note_t(n)} for n in notes.get("commands", [])],
        "links": [{"url": n["url"], "label": n.get("label") or n["url"], "segment_idx": int(n["segment_idx"]), "t": note_t(n)} for n in notes.get("links", [])],
    }
    doc = {
        "schema_version": "1.0",
        "lecture": {
            "id": lecture_id, "title": info.get("title", ""), "video_id": info.get("id", ""), "source_url": info.get("webpage_url", ""),
            "duration": {"orig": round(total, 3), "edit": round(edited_duration, 3)},
            "pipeline": {"transcript_source": "youtube_json3", "policy": "speech_only_v1",
                         "generated_at": datetime.now(KST).isoformat(timespec="seconds")},
        },
        "files": {"original": "original.mp4", "edited": "edited.mp4", "thumbs_dir": "thumbs/"},
        "segments": segments, "cuts": cuts_out, "chapters": chapters, "notes": notes_out,
    }
    if glossary:
        doc["glossary"] = [{"term": g["term"], "definition": g["definition"],
                            **({"analogy": g["analogy"]} if g.get("analogy") else {}),
                            "segment_idx": int(g["segment_idx"]), "t": note_t(g)} for g in glossary]
    errs = validate_lecture(doc)
    if errs:
        raise ValueError("lecture.json invalid:\n" + "\n".join(errs))
    return doc


def _ffprobe_duration(p: Path) -> float:
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(p)]).decode().strip())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("build", "outline", "notes", "info", "original", "edited", "out"):
        ap.add_argument(f"--{k}", required=True)
    ap.add_argument("--glossary", help="선택 — 용어집 패스 산출물 glossary.json")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    doc = build_lecture(
        Path(a.build),
        json.loads(Path(a.outline).read_text(encoding="utf-8")),
        json.loads(Path(a.notes).read_text(encoding="utf-8")),
        json.loads(Path(a.info).read_text(encoding="utf-8")),
        _ffprobe_duration(Path(a.edited)), None,
        json.loads(Path(a.glossary).read_text(encoding="utf-8")) if a.glossary else None,
    )
    for ch in doc["chapters"]:
        thumbs.grab(Path(a.original), ch["t"]["orig"][0], out / ch["thumb"])
    (out / "lecture.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"lecture.json ok · segments={len(doc['segments'])} cuts={len(doc['cuts'])} "
          f"chapters={len(doc['chapters'])} glossary={len(doc.get('glossary', []))} → {out}")


if __name__ == "__main__":
    main()
