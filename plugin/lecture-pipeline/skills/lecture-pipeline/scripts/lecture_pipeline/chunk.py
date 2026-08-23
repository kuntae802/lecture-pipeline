"""indexed.md 를 10~12분 창으로 나눈다. 문장 경계에서만 자르고, 각 창 앞에 직전 2문장을 읽기전용 문맥으로 붙인다.

사용: python3 <스킬>/scripts/lp.py chunk --build workspace/build/01/youtube --out workspace/build/01/chunks
산출: chunks/NN.md (편집 브리프 입력) + chunks/manifest.json
      manifest 항목 = {"n", "file", "word_from", "word_to", "start", "end", "ctx_word_from"}
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LINE = re.compile(r"^\[\s*(\d+)\] \[\s*([\d.]+)-\s*([\d.]+)\] ")


MIN_TAIL_SEC = 90   # 이보다 짧은 꼬리 청크는 앞 청크에 합친다(1단어짜리 청크에 LLM 을 쓰지 않도록)


def plan_chunks(sentences: list[dict], target_sec: float = 660, max_sec: float = 780, ctx_sentences: int = 2) -> list[dict]:
    """문장 리스트를 target_sec 근처(최대 max_sec)에서 문장 경계로 자른다. 문맥 = 직전 ctx_sentences 문장."""
    chunks: list[dict] = []
    cur: list[int] = []  # sentences 인덱스(0-based)

    def close() -> None:
        first, last = sentences[cur[0]], sentences[cur[-1]]
        ci = max(0, cur[0] - ctx_sentences)
        chunks.append({
            "n": len(chunks) + 1, "file": f"{len(chunks) + 1:02d}.md",
            "word_from": first["word_from"], "word_to": last["word_to"],
            "start": first["start"], "end": last["end"], "ctx_word_from": sentences[ci]["word_from"],
        })

    for i, s in enumerate(sentences):
        if cur:
            head = sentences[cur[0]]
            if s["end"] - head["start"] > max_sec or s["start"] - head["start"] >= target_sec:
                close()
                cur = []
        cur.append(i)
    if cur:
        close()

    # 마지막 조각이 너무 짧으면(끝인사 몇 마디 등) 앞 청크로 흡수한다 — 경계는 그대로 유지된다.
    if len(chunks) > 1 and chunks[-1]["end"] - chunks[-1]["start"] < MIN_TAIL_SEC:
        tail = chunks.pop()
        chunks[-1]["word_to"] = tail["word_to"]
        chunks[-1]["end"] = tail["end"]
    return chunks


def slice_indexed(md: str, ctx_from: int, word_from: int, word_to: int) -> str:
    """indexed.md 에서 [ctx_from, word_to] 구간만 뽑되 문맥 구간과 편집 구간을 헤더로 가른다. 멈춤 표시 줄은 따라온다."""
    out: list[str] = []
    mode: str | None = None  # None | "ctx" | "edit"
    for ln in md.splitlines():
        m = LINE.match(ln)
        if m:
            n = int(m.group(1))
            if n < ctx_from or n > word_to:
                mode = None
                continue
            new_mode = "ctx" if n < word_from else "edit"
            if new_mode != mode:
                if out:
                    out.append("")
                out.append("## CONTEXT (read-only, do not cut)" if new_mode == "ctx" else "## EDITABLE RANGE")
                mode = new_mode
            out.append(ln)
        elif mode and ln.strip().startswith("_("):
            out.append(ln)
    return "\n".join(out) + "\n"


def write_chunks(build_dir: Path, out_dir: Path) -> list[dict]:
    sentences = json.loads((build_dir / "sentences.json").read_text(encoding="utf-8"))
    md = (build_dir / "indexed.md").read_text(encoding="utf-8")
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks = plan_chunks(sentences)
    for c in chunks:
        hdr = [
            f"# Chunk {c['n']:02d} — words {c['word_from']}..{c['word_to']} · {c['start']:.1f}s..{c['end']:.1f}s",
            "# Lines: [N] [start-end] word · `_(silence Xs)_` = pause · CONTEXT block is read-only",
            "",
        ]
        (out_dir / c["file"]).write_text("\n".join(hdr) + slice_indexed(md, c["ctx_word_from"], c["word_from"], c["word_to"]), encoding="utf-8")
    (out_dir / "manifest.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ch = write_chunks(Path(a.build), Path(a.out))
    print(f"{len(ch)} chunks → {a.out}")


if __name__ == "__main__":
    main()
