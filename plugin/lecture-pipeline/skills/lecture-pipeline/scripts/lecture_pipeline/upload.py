"""산출물 폴더 → 뷰어 웹 업로드. 표준 라이브러리만 쓴다.

사용: python3 <스킬>/scripts/lp.py upload --out workspace/out/<ID> [--api URL] [--token T]
      (--api 를 생략하면 VCU_API 환경변수, 그것도 없으면 config.DEFAULT_API 로 간다)

원본·편집본이 합쳐 1~2GB 라 **파일을 메모리에 올리지 않고 흘려보낸다** — multipart 본문의
길이를 미리 계산해 Content-Length 로 알린 뒤, 파일을 1MB 씩 읽어 소켓에 그대로 쓴다.

올릴 파일은 lecture.json 의 `files` 필드가 가리키는 이름을 따른다. 파이프라인 버전마다
파일명 규칙이 달라도(`01.original.mp4` ↔ `original.mp4`) 이 한 곳만 보면 된다.

업로드는 멱등이 아니다 — 강의 id 가 조립할 때마다 새로 생기므로 같은 영상을 다시 올리면
뷰어 목록에 새 항목으로 쌓인다(2026-08-23 결정).
"""
from __future__ import annotations

import argparse
import http.client
import json
import shutil
import ssl
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from . import config, jobs

CHUNK = 1 << 20
POLL_EVERY = 5.0

# 서버가 받는 필드 이름 ↔ lecture.json files 키. thumbs_zip 만 선택이다.
FIELDS = (
    ("lecture_json", None, "application/json"),
    ("original", "original", "video/mp4"),
    ("edited", "edited", "video/mp4"),
    ("thumbs_zip", None, "application/zip"),
)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def ensure_thumbs_zip(out_dir: Path) -> Path | None:
    """thumbs.zip 이 없고 thumbs/ 가 있으면 만들어 준다. 썸네일이 아예 없으면 None."""
    zp = out_dir / "thumbs.zip"
    if zp.exists():
        return zp
    if not (out_dir / "thumbs").is_dir():
        return None
    shutil.make_archive(str(out_dir / "thumbs"), "zip", str(out_dir), "thumbs")
    return zp if zp.exists() else None


def parts_for(out_dir: Path) -> list[tuple[str, Path, str]]:
    """(필드명, 파일 경로, content-type) 목록. lecture.json 의 files 를 따른다."""
    doc = json.loads((out_dir / "lecture.json").read_text(encoding="utf-8"))
    files = doc.get("files") or {}
    out: list[tuple[str, Path, str]] = []
    for field, files_key, ctype in FIELDS:
        if field == "lecture_json":
            p = out_dir / "lecture.json"
        elif field == "thumbs_zip":
            z = ensure_thumbs_zip(out_dir)
            if z is None:
                continue
            p = z
        else:
            p = out_dir / str(files.get(files_key) or f"{files_key}.mp4")
        if not p.exists():
            raise FileNotFoundError(f"업로드할 파일이 없다: {p}")
        out.append((field, p, ctype))
    return out


def multipart_plan(parts: list[tuple[str, Path, str]], boundary: str) -> tuple[list[tuple[bytes, Path]], bytes, int]:
    """각 파트의 머리말과 전체 Content-Length 를 미리 계산한다(파일은 읽지 않는다).

    반환 = ([(머리말 bytes, 파일 경로)], 맺음말 bytes, Content-Length)."""
    heads: list[tuple[bytes, Path]] = []
    total = 0
    for field, path, ctype in parts:
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode()
        heads.append((head, path))
        total += len(head) + path.stat().st_size + 2  # 파트 끝 CRLF
    tail = f"--{boundary}--\r\n".encode()
    return heads, tail, total + len(tail)


def _connect(url: str) -> tuple[http.client.HTTPConnection, str]:
    u = urlsplit(url)
    host = u.hostname or ""
    port = u.port
    base = u.path.rstrip("/")
    if u.scheme == "https":
        return http.client.HTTPSConnection(host, port, timeout=600, context=ssl.create_default_context()), base
    return http.client.HTTPConnection(host, port, timeout=600), base


def upload(out_dir: Path, api: str, token: str = "") -> dict:
    parts = parts_for(out_dir)
    boundary = uuid.uuid4().hex
    heads, tail, length = multipart_plan(parts, boundary)
    _log(f"업로드 {length / 1e9:.2f}GB → {api}/lectures")

    conn, base = _connect(api)
    conn.putrequest("POST", f"{base}/lectures")
    conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
    conn.putheader("Content-Length", str(length))
    if token:
        conn.putheader("X-Admin-Token", token)
    conn.endheaders()

    sent = 0
    last = 0.0
    for head, path in heads:
        conn.send(head)
        sent += len(head)
        with path.open("rb") as f:
            while chunk := f.read(CHUNK):
                conn.send(chunk)
                sent += len(chunk)
                now = time.monotonic()
                if now - last > 10:  # 10초마다 한 줄 — 대용량이라 진행이 멈춘 건지 알 수 있어야 한다
                    _log(f"  … {sent / length * 100:5.1f}%  ({sent / 1e9:.2f}/{length / 1e9:.2f}GB)")
                    last = now
        conn.send(b"\r\n")
        sent += 2
    conn.send(tail)

    resp = conn.getresponse()
    body = resp.read().decode("utf-8", "replace")
    conn.close()
    if resp.status >= 400:
        raise RuntimeError(f"업로드 실패 {resp.status}: {body[:800]}")
    return json.loads(body)


def wait_ready(api: str, lecture_id: str, timeout: float = 1800) -> dict:
    """적재·임베딩이 끝날 때까지 기다린다. 임베딩 모델이 없으면 서버가 키워드 검색만으로 ready 를 낸다."""
    t0 = time.monotonic()
    seen = ""
    while time.monotonic() - t0 < timeout:
        conn, base = _connect(api)
        conn.request("GET", f"{base}/lectures/{lecture_id}/status")
        r = conn.getresponse()
        st = json.loads(r.read().decode("utf-8", "replace")) if r.status < 400 else {}
        conn.close()
        s = str(st.get("ingest_status", ""))
        if s != seen:
            _log(f"  적재 상태: {s}")
            seen = s
        if s == "ready":
            return st
        if s == "failed":
            raise RuntimeError(f"적재 실패: {str(st.get('ingest_error'))[:800]}")
        if s == "embedding" and st.get("embed_total"):
            _log(f"  임베딩 {st.get('embed_done')}/{st.get('embed_total')}")
        time.sleep(POLL_EVERY)
    raise TimeoutError(f"{timeout:.0f}초 안에 ready 가 되지 않았다(마지막 상태: {seen or '알 수 없음'})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="산출물 폴더 (workspace/out/<ID>)")
    ap.add_argument("--api", default="", help="뷰어 API 주소 (생략하면 VCU_API 환경변수, 그것도 없으면 내장 기본값)")
    ap.add_argument("--token", default="", help="관리자 토큰 (생략하면 VCU_API_TOKEN 환경변수)")
    ap.add_argument("--timeout", type=float, default=1800, help="ready 까지 기다릴 최대 초")
    ap.add_argument("--no-wait", action="store_true", help="업로드만 하고 적재 완료를 기다리지 않는다")
    a = ap.parse_args()
    api_url, tok = config.api(a.api), config.token(a.token)

    res = upload(Path(a.out), api_url, tok)
    lid = str(res.get("id", ""))
    try:  # 진행도 카드에서 결과 강의로 이어주기 위한 부가 정보. 실패해도 무방하다.
        doc = json.loads((Path(a.out) / "lecture.json").read_text(encoding="utf-8"))
        jobs.report("upload", "running", "적재 대기", lecture_id=lid, title=doc["lecture"].get("title", ""))
    except Exception:
        pass
    _log(f"업로드 완료 · 강의 id = {lid}")
    if a.no_wait:
        print(lid)
        return
    st = wait_ready(api_url, lid, a.timeout)
    _log(f"적재 완료 · 임베딩 {st.get('embed_done')}/{st.get('embed_total')}")
    print(lid)


if __name__ == "__main__":
    main()
