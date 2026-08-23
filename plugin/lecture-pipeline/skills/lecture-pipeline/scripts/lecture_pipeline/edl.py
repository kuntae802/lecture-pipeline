"""컷 → keep 세그먼트 → 컨테이너 안에서 돌릴 ffmpeg 렌더 스크립트.

세그먼트별 재인코딩(NVENC 우선, 명시 시 libx264) + 경계 80ms 오디오 페이드 + concat demuxer `-c copy`.
사용(고급/원격): python3 <스킬>/scripts/lp.py edl --build workspace/build/01/youtube --duration 12425.8 --out render.sh [--encoder libx264]
로컬 렌더는 render.py 가 ffmpeg 를 직접 부른다 — 이 모듈은 원격 컨테이너용 셸 스크립트를 만들 때만 쓴다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FADE = 0.08


def keep_segments(duration: float, cuts) -> list[tuple[float, float]]:
    keeps: list[tuple[float, float]] = []
    pos = 0.0
    for s, e in sorted(cuts):
        if s > pos:
            keeps.append((round(pos, 3), round(s, 3)))
        pos = max(pos, e)
    if pos < duration:
        keeps.append((round(pos, 3), round(duration, 3)))
    return keeps


def _venc(encoder: str) -> str:
    if encoder == "h264_nvenc":
        return "-c:v h264_nvenc -preset p4 -rc vbr -cq 23 -b:v 0"
    return "-c:v libx264 -preset veryfast -crf 21"


def write_render_script(keeps, src: str, out: str, workdir: str, encoder: str = "h264_nvenc") -> str:
    lines = [
        "#!/bin/bash",
        "set -euo pipefail",
        f"mkdir -p {workdir}",
        f"rm -f {workdir}/seg_*.mp4 {workdir}/list.txt",
        f'echo "[render] {len(keeps)} segments encoder={encoder}"',
    ]
    for i, (s, e) in enumerate(keeps):
        dur = e - s
        af = f"afade=t=in:st=0:d={FADE},afade=t=out:st={max(0.0, dur - FADE):.3f}:d={FADE}"
        lines.append(
            f"ffmpeg -hide_banner -loglevel error -y -ss {s:.3f} -to {e:.3f} -i {src} {_venc(encoder)} "
            f"-c:a aac -b:a 160k -af \"{af}\" -movflags +faststart {workdir}/seg_{i:04d}.mp4 "
            f'&& echo "[render] seg {i + 1}/{len(keeps)} ok"'
        )
        lines.append(f"echo \"file '{workdir}/seg_{i:04d}.mp4'\" >> {workdir}/list.txt")
    lines.append(f"ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i {workdir}/list.txt -c copy -movflags +faststart {out}")
    lines.append(f'echo "[render] done → {out}"')
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", required=True)
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--encoder", default="h264_nvenc", choices=["h264_nvenc", "libx264"])
    ap.add_argument("--src", default="/in/01.mp4")
    ap.add_argument("--dst", default="/out/01.edited.mp4")
    ap.add_argument("--workdir", default="/work")
    a = ap.parse_args()
    cuts = [tuple(c["orig"]) for c in json.loads((Path(a.build) / "cuts.json").read_text(encoding="utf-8"))]
    keeps = keep_segments(a.duration, cuts)
    Path(a.out).write_text(write_render_script(keeps, a.src, a.dst, a.workdir, a.encoder), encoding="utf-8")
    print(f"{len(keeps)} segments → {a.out}")


if __name__ == "__main__":
    main()
