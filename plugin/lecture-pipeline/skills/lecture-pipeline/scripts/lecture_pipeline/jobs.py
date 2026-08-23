"""작업 진행도를 뷰어 웹에 알린다. 표준 라이브러리만.

**작업 폴더 하나 = job 하나.** 1단계(fetch)가 job id 를 새로 발급해 `workspace/.job` 에 남기고,
이후 모든 명령은 그 파일을 읽어 자기 단계를 보고한다. 그래서 폴더가 다르면 자연히 다른 job 이고,
같은 영상을 다시 돌리면 새 job 이 된다(중간 단계부터 재시작하면 같은 job 을 이어간다).

**보고 실패는 삼킨다.** 네트워크나 뷰어 사정 때문에 강의 제작이 멈추면 안 된다 —
`VCU_API` 가 없으면 아무것도 하지 않고, 있어도 3초 안에 응답이 없으면 그냥 넘어간다.
"""
from __future__ import annotations

import http.client
import json
import os
import ssl
from pathlib import Path
from urllib.parse import urlsplit

from .ids import stamped_id

JOB_FILE = Path("workspace/.job")
TIMEOUT = 3.0

# 화면에 순서대로 그려지는 단계. lp.py 서브커맨드 이름과 판단 단계(edit·outline·glossary)를 합친 것.
STEPS = ("fetch", "preprocess", "chunk", "edit", "merge", "outline", "glossary", "render", "assemble", "upload")


def api() -> str:
    return os.environ.get("VCU_API", "").rstrip("/")


def start(video_id: str, url: str = "") -> dict:
    """새 작업을 연다. fetch 가 실행될 때마다 부르므로 재작업이면 새 job 이 된다."""
    job = {"job_id": stamped_id(video_id), "video_id": video_id, "url": url}
    JOB_FILE.parent.mkdir(parents=True, exist_ok=True)
    JOB_FILE.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    return job


def load() -> dict | None:
    try:
        return json.loads(JOB_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def report(step: str, status: str, detail: str = "", **extra) -> None:
    """단계 상태를 보낸다. 실패는 조용히 넘긴다(파이프라인을 막지 않는다)."""
    base = api()
    job = load()
    if not base or not job:
        return
    payload = {"step": step, "status": status, "detail": detail,
               "video_id": job.get("video_id", ""), "url": job.get("url", ""), **extra}
    body = json.dumps(payload, ensure_ascii=False).encode()
    try:
        u = urlsplit(base)
        cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        kw = {"context": ssl.create_default_context()} if u.scheme == "https" else {}
        conn = cls(u.hostname or "", u.port, timeout=TIMEOUT, **kw)
        conn.request("POST", f"{u.path.rstrip('/')}/jobs/{job['job_id']}", body,
                     {"Content-Type": "application/json", "Content-Length": str(len(body))})
        conn.getresponse().read()
        conn.close()
    except Exception:
        pass


def main() -> None:
    """`lp.py progress --step edit --detail 8/19` — lp.py 밖에서 도는 판단 단계용."""
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", required=True, choices=STEPS)
    ap.add_argument("--status", default="running", choices=["running", "done", "failed"])
    ap.add_argument("--detail", default="", help='예: "8/19"')
    a = ap.parse_args()
    report(a.step, a.status, a.detail)
