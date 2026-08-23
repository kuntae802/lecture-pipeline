"""lecture.json 검증 — schema/lecture.schema.json 의 규칙을 stdlib 로 검사한다(의존성 0).

불변식: (1) 컷 구간 안에 완전히 들어간 세그먼트는 edit == null (2) cuts 는 겹치지 않고 orig 기준 정렬
(3) chapters.segments 범위는 segments idx 안 (4) category/confidence enum (5) schema_version == "1.0".
웹 ingest(pydantic)도 같은 스키마 파일을 읽어 같은 규칙을 적용한다(lockstep).
"""
from __future__ import annotations

import json
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "lecture.schema.json"
SCHEMA_VERSION = "1.0"
CATEGORIES = {"misstatement", "duplicate"}
CONFIDENCES = {"high", "medium"}

MINIMAL_EXAMPLE = {
    "schema_version": "1.0",
    "lecture": {
        "id": "v-0823-1652", "title": "t", "video_id": "v", "source_url": "https://youtu.be/v",
        "duration": {"orig": 10.0, "edit": 10.0},
        "pipeline": {"transcript_source": "youtube_json3", "policy": "speech_only_v1", "generated_at": "2026-08-23T00:00:00+09:00"},
    },
    "files": {"original": "01.original.mp4", "edited": "01.edited.mp4", "thumbs_dir": "thumbs/"},
    "segments": [{"idx": 1, "text": "안녕하세요.", "t": {"orig": [0.0, 2.0], "edit": [0.0, 2.0]}}],
    "cuts": [],
    "chapters": [{"id": "1", "level": 1, "title": "도입", "summary": "s", "t": {"orig": [0.0, 10.0], "edit": [0.0, 10.0]},
                  "segments": [1, 1], "thumb": "thumbs/ch01.jpg", "children": []}],
    "notes": {"commands": [], "links": []},
}


def _span(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v) and v[0] <= v[1]


def validate_lecture(doc: dict) -> list[str]:
    errs: list[str] = []
    if doc.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version must be '{SCHEMA_VERSION}'")
    missing = [k for k in ("lecture", "files", "segments", "cuts", "chapters", "notes") if k not in doc]
    if missing:
        errs.extend(f"missing top-level '{k}'" for k in missing)
        return errs

    lec = doc["lecture"]
    for k in ("id", "title", "video_id", "source_url", "duration", "pipeline"):
        if k not in lec:
            errs.append(f"lecture.{k} missing")
    for k in ("original", "edited", "thumbs_dir"):
        if k not in doc["files"]:
            errs.append(f"files.{k} missing")

    cuts = [c for c in doc["cuts"] if _span(c.get("orig"))]
    for i, c in enumerate(doc["cuts"]):
        if not _span(c.get("orig")):
            errs.append(f"cuts[{i}].orig invalid")
            continue
        if c.get("category") not in CATEGORIES:
            errs.append(f"cuts[{i}].category invalid: {c.get('category')!r}")
        if c.get("confidence") not in CONFIDENCES:
            errs.append(f"cuts[{i}].confidence invalid: {c.get('confidence')!r}")
        for k in ("id", "edit_at", "removed_text", "note"):
            if k not in c:
                errs.append(f"cuts[{i}].{k} missing")
    ordered = sorted(cuts, key=lambda c: c["orig"][0])
    for p, q in zip(ordered, ordered[1:]):
        if q["orig"][0] < p["orig"][1]:
            errs.append(f"cuts overlap: {p['orig']} vs {q['orig']}")

    n_seg = len(doc["segments"])
    for i, s in enumerate(doc["segments"]):
        t = s.get("t") or {}
        if not isinstance(s.get("idx"), int) or not isinstance(s.get("text"), str):
            errs.append(f"segments[{i}] idx/text invalid")
        if not _span(t.get("orig")):
            errs.append(f"segments[{i}].t.orig invalid")
            continue
        e = t.get("edit")
        if e is not None and not _span(e):
            errs.append(f"segments[{i}].t.edit invalid")
        inside = any(c["orig"][0] <= t["orig"][0] and t["orig"][1] <= c["orig"][1] for c in cuts)
        if inside and e is not None:
            errs.append(f"segments[{i}].t.edit must be null (inside a cut)")

    def walk(ch: dict, path: str) -> None:
        for k in ("id", "level", "title", "summary", "t", "segments"):
            if k not in ch:
                errs.append(f"{path}.{k} missing")
        if ch.get("level") not in (1, 2):
            errs.append(f"{path}.level must be 1|2")
        t = ch.get("t") or {}
        if not _span(t.get("orig")) or (t.get("edit") is not None and not _span(t.get("edit"))):
            errs.append(f"{path}.t invalid")
        r = ch.get("segments")
        if not (isinstance(r, list) and len(r) == 2 and all(isinstance(x, int) for x in r) and 1 <= r[0] <= r[1] <= n_seg):
            errs.append(f"{path}.segments out of range {r} (n={n_seg})")
        for j, sub in enumerate(ch.get("children") or []):
            walk(sub, f"{path}.children[{j}]")

    for i, ch in enumerate(doc["chapters"]):
        walk(ch, f"chapters[{i}]")

    for k in ("commands", "links"):
        if k not in doc["notes"]:
            errs.append(f"notes.{k} missing")

    # glossary 는 선택 — 있으면 형식을 검사한다(없는 산출물도 유효하다)
    gloss = doc.get("glossary")
    if gloss is not None:
        if not isinstance(gloss, list):
            errs.append("glossary must be an array")
        else:
            for i, g in enumerate(gloss):
                for k in ("term", "definition", "segment_idx", "t"):
                    if k not in g:
                        errs.append(f"glossary[{i}].{k} missing")
                if not isinstance(g.get("term"), str) or not g.get("term", "").strip():
                    errs.append(f"glossary[{i}].term empty")
                idx = g.get("segment_idx")
                if not (isinstance(idx, int) and 1 <= idx <= n_seg):
                    errs.append(f"glossary[{i}].segment_idx out of range {idx} (n={n_seg})")
                t = g.get("t") or {}
                if not _span(t.get("orig")) or (t.get("edit") is not None and not _span(t.get("edit"))):
                    errs.append(f"glossary[{i}].t invalid")
    return errs


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
