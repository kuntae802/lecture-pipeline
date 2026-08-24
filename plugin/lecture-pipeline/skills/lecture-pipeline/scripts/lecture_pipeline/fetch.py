"""yt-dlp 래퍼. 이미 받은 파일은 건너뛴다(멱등).

사용: python3 <스킬>/scripts/lp.py fetch https://youtu.be/ID
산출: workspace/raw/<ID>/source.mp4 (1080p 이하 최고 화질) · source.ko.json3 (한국어 자동자막) · source.info.json
폴더가 video id 하나로 정해지므로 같은 영상을 다시 돌리면 받아둔 원본을 그대로 재사용한다.
주의: 2026-08 기준 yt-dlp 는 JS 런타임이 있어야 미디어 URL 403 을 피한다 → `--js-runtimes node` 고정.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from . import jobs


VIDEO_FORMAT = (
    "bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/"
    "bv*[height<=1080]+ba/"
    "b[height<=1080]/b"
)


def video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
    return m.group(1) if m else url


def fetch(url: str, root: Path = Path("workspace/raw")) -> Path:
    vid = video_id(url)
    # 여기가 작업의 시작점이다 — job id 를 새로 발급해 workspace/.job 에 남긴다.
    jobs.start(vid, url)
    jobs.report("fetch", "running")
    d = root / vid
    d.mkdir(parents=True, exist_ok=True)
    common = ["yt-dlp", "--js-runtimes", "node", "--no-progress", "-o", f"{d}/source.%(ext)s"]
    if not (d / "source.ko.json3").exists() or not (d / "source.info.json").exists():
        subprocess.run(common + ["--skip-download", "--write-auto-subs", "--sub-langs", "ko", "--sub-format", "json3",
                                 "--write-info-json", url], check=True)
    # 제목은 여기서부터 알 수 있다 — 이걸 알려 줘야 진행도 카드가 영상 id 대신 강의 제목으로 뜬다.
    try:
        info = json.loads((d / "source.info.json").read_text(encoding="utf-8"))
        jobs.report("fetch", "running", title=str(info.get("title", ""))[:300])
    except Exception:
        pass
    if not (d / "source.mp4").exists():
        # 특정 itag(137+140)를 못박으면 그 화질이 없는 영상에서 실패한다 — 폴백 사슬로 고른다.
        # 브라우저 호환이 가장 좋은 avc1+m4a 를 먼저, 없으면 아무 조합, 그래도 없으면 단일 파일.
        subprocess.run(common + ["-f", VIDEO_FORMAT, "--merge-output-format", "mp4", url], check=True)
    return d


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--root", default="workspace/raw", help="작업 폴더 기준 저장 위치")
    a = ap.parse_args()
    print(fetch(a.url, Path(a.root)))


if __name__ == "__main__":
    main()
