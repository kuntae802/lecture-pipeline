"""청크별 편집 결과(cuts/corrections)를 합쳐 cuts.json·corrections.json 을 만든다.

검증 실패는 errors 로 돌려주고(파일은 쓰지 않음) — 실패한 청크만 편집 패스를 다시 돌린다.
규칙: from_idx ≤ to_idx · 인덱스는 그 청크의 편집 가능 범위 안(문맥 구간 컷 금지) · 컷 길이 ≥ MIN_CUT_SEC(미세 컷 금지 정책)
      · category enum · 컷 겹침 금지. corrections 는 idx 중복 시 마지막 승.
텍스트 모드(--no-cuts): 컷 파일을 읽지 않고(있어도 무시) cuts=[] 로 고정, 청크마다 corrections 파일 존재를 강제한다.
교정을 반영한 문장 파일 sentences.corrected.json 도 함께 쓴다 — 구조화·용어집 패스가 이걸 읽어야
잘못 인식된 용어가 목차 제목과 용어집에 그대로 들어가지 않는다. 원본 sentences.json 은 건드리지 않고
매번 원본에서 새로 만들므로 여러 번 돌려도 결과가 같다.
사용: python3 <스킬>/scripts/lp.py merge --build workspace/build/01/youtube --chunks workspace/build/01/chunks
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

MIN_CUT_SEC = 0.8
CATEGORIES = {"misstatement", "duplicate"}
CONFIDENCES = {"high", "medium"}


def _word_index(words: list[dict]) -> dict[int, dict]:
    """audio_event 를 제외한 1-based 단어 번호 → word."""
    out, n = {}, 0
    for w in words:
        if w.get("type", "word") == "word":
            n += 1
            out[n] = w
    return out


def merge(build_dir: Path, chunks_dir: Path, no_cuts: bool = False) -> tuple[list, list, list[str]]:
    words = _word_index(json.loads((build_dir / "words.json").read_text(encoding="utf-8"))["words"])
    manifest = json.loads((chunks_dir / "manifest.json").read_text(encoding="utf-8"))
    cuts: list[dict] = []
    corrections: dict[int, dict] = {}
    errors: list[str] = []

    for m in manifest:
        n = m["n"]
        if not no_cuts:
            cf = chunks_dir / f"{n:02d}.cuts.json"
            if not cf.exists():
                errors.append(f"chunk {n:02d}: cuts file missing")
                continue
            try:
                chunk_cuts = json.loads(cf.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"chunk {n:02d}: cuts file not valid JSON ({exc})")
                continue
            for k, c in enumerate(chunk_cuts):
                a, b = c.get("from_idx"), c.get("to_idx")
                tag = f"chunk {n:02d} cut#{k}"
                if not (isinstance(a, int) and isinstance(b, int) and a <= b):
                    errors.append(f"{tag}: bad indices {a}-{b}")
                    continue
                if a < m["word_from"] or b > m["word_to"]:
                    errors.append(f"{tag}: indices {a}-{b} outside editable range {m['word_from']}-{m['word_to']} (context cut?)")
                    continue
                if a not in words or b not in words:
                    errors.append(f"{tag}: indices {a}-{b} not in transcript")
                    continue
                if c.get("category") not in CATEGORIES:
                    errors.append(f"{tag}: category {c.get('category')!r} invalid")
                    continue
                s, e = words[a]["start"], words[b]["end"]
                if e - s < MIN_CUT_SEC:
                    errors.append(f"{tag}: too short ({e - s:.2f}s < {MIN_CUT_SEC}s) — {a}-{b}")
                    continue
                conf = c.get("confidence", "medium")
                cuts.append({
                    "from_idx": a, "to_idx": b, "orig": [round(s, 3), round(e, 3)],
                    "category": c["category"], "confidence": conf if conf in CONFIDENCES else "medium",
                    "note": c.get("note", ""),
                    "removed_text": " ".join(words[i]["text"] for i in range(a, b + 1) if i in words),
                })
        pf = chunks_dir / f"{n:02d}.corrections.json"
        if no_cuts and not pf.exists():
            errors.append(f"chunk {n:02d}: corrections file missing")
            continue
        if pf.exists():
            try:
                rows = json.loads(pf.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"chunk {n:02d}: corrections file not valid JSON ({exc})")
                rows = []
            for r in rows:
                idx = r.get("idx")
                if isinstance(idx, int) and idx in words and isinstance(r.get("to"), str) and r["to"].strip():
                    corrections[idx] = {"idx": idx, "from": r.get("from", words[idx]["text"]), "to": r["to"].strip()}

    cuts.sort(key=lambda c: c["orig"][0])
    for p, q in zip(cuts, cuts[1:]):
        if q["orig"][0] < p["orig"][1]:
            errors.append(f"cuts overlap: {p['from_idx']}-{p['to_idx']} {p['orig']} vs {q['from_idx']}-{q['to_idx']} {q['orig']}")
    for i, c in enumerate(cuts, 1):
        c["id"] = i
    return cuts, [corrections[k] for k in sorted(corrections)], errors


def corrected_sentences(sentences: list[dict], words: dict[int, dict], corrections: list[dict]) -> list[dict]:
    """문장 텍스트에 표기 교정을 반영한 사본. 문장 텍스트는 전처리와 같은 규칙(단어를 공백으로 잇기)으로
    다시 만든다 — 조립 단계(assemble._segment_text)가 쓰는 규칙과도 같다."""
    corr = {c["idx"]: c["to"] for c in corrections}
    return [{**s, "text": " ".join(corr.get(i, words[i]["text"]) for i in range(s["word_from"], s["word_to"] + 1) if i in words)}
            for s in sentences]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", required=True)
    ap.add_argument("--chunks", required=True)
    ap.add_argument("--no-cuts", action="store_true", help="텍스트 모드 — 교정만 합치고 빈 cuts.json 을 쓴다")
    a = ap.parse_args()
    cuts, corr, errs = merge(Path(a.build), Path(a.chunks), a.no_cuts)
    if errs:
        print("\n".join("ERROR " + e for e in errs))
        raise SystemExit(1)
    # 세 파일을 다 계산한 뒤에 쓴다 — 중간에 실패하면 아무것도 쓰지 않는다(모듈 docstring 의 약속).
    build = Path(a.build)
    sents = json.loads((build / "sentences.json").read_text(encoding="utf-8"))
    words = _word_index(json.loads((build / "words.json").read_text(encoding="utf-8"))["words"])
    fixed = corrected_sentences(sents, words, corr)
    (build / "cuts.json").write_text(json.dumps(cuts, ensure_ascii=False, indent=1), encoding="utf-8")
    (build / "corrections.json").write_text(json.dumps(corr, ensure_ascii=False, indent=1), encoding="utf-8")
    (build / "sentences.corrected.json").write_text(json.dumps(fixed, ensure_ascii=False, indent=1), encoding="utf-8")
    removed = sum(c["orig"][1] - c["orig"][0] for c in cuts)
    print(f"cuts={len(cuts)} corrections={len(corr)} removed={removed:.1f}s")


if __name__ == "__main__":
    main()
