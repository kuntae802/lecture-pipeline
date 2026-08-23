"""챕터 시작 프레임(원본 시각)을 jpg 로 뽑는다. 110 CPU ffmpeg 로 충분(수십 장)."""
from __future__ import annotations

import subprocess
from pathlib import Path


def grab(src: Path, t: float, out: Path, width: int = 640) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(src),
         "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", str(out)],
        check=True,
    )
