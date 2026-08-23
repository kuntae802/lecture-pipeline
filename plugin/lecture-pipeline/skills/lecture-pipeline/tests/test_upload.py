"""업로드는 1~2GB 를 흘려보내므로 Content-Length 계산이 틀리면 소켓이 그대로 멈춘다.
계산을 단위로 검증하고, 실제 왕복은 표준 라이브러리 스텁 서버로 한 번 확인한다."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from lecture_pipeline.upload import ensure_thumbs_zip, multipart_plan, parts_for, upload, wait_ready

DOC = {"files": {"original": "01.original.mp4", "edited": "01.edited.mp4", "thumbs_dir": "thumbs/"}}


def _out(tmp_path, doc=DOC, thumbs=True, orig=b"ORIGINAL", edited=b"EDITED"):
    d = tmp_path / "out"
    d.mkdir()
    (d / "lecture.json").write_text(json.dumps(doc), encoding="utf-8")
    (d / doc["files"]["original"]).write_bytes(orig)
    (d / doc["files"]["edited"]).write_bytes(edited)
    if thumbs:
        (d / "thumbs").mkdir()
        (d / "thumbs" / "ch01.jpg").write_bytes(b"JPG")
    return d


def test_parts_follow_the_files_field_not_a_fixed_name(tmp_path):
    d = _out(tmp_path, {"files": {"original": "original.mp4", "edited": "edited.mp4", "thumbs_dir": "thumbs/"}})
    got = {field: p.name for field, p, _ in parts_for(d)}
    assert got["original"] == "original.mp4" and got["edited"] == "edited.mp4"


def test_parts_accept_the_older_numbered_filenames(tmp_path):
    got = {field: p.name for field, p, _ in parts_for(_out(tmp_path))}
    assert got["original"] == "01.original.mp4" and got["lecture_json"] == "lecture.json"


def test_thumbs_zip_is_built_from_the_thumbs_folder_when_missing(tmp_path):
    d = _out(tmp_path)
    assert ensure_thumbs_zip(d) == d / "thumbs.zip"
    assert "thumbs_zip" in {field for field, _, _ in parts_for(d)}


def test_thumbs_are_simply_skipped_when_there_are_none(tmp_path):
    d = _out(tmp_path, thumbs=False)
    assert ensure_thumbs_zip(d) is None
    assert "thumbs_zip" not in {field for field, _, _ in parts_for(d)}


def test_missing_file_fails_before_any_bytes_go_out(tmp_path):
    d = _out(tmp_path)
    (d / "01.edited.mp4").unlink()
    with pytest.raises(FileNotFoundError):
        parts_for(d)


def test_content_length_matches_the_bytes_actually_written(tmp_path):
    parts = parts_for(_out(tmp_path))
    heads, tail, length = multipart_plan(parts, "BOUND")
    body = b"".join(head + path.read_bytes() + b"\r\n" for head, path in heads) + tail
    assert len(body) == length


# ── 실제 왕복 ─────────────────────────────────────────────────────────────────
class _Stub(BaseHTTPRequestHandler):
    received: dict = {}
    status_seq: list = []

    def log_message(self, *a):  # 테스트 출력 오염 방지
        pass

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        _Stub.received = {"body": self.rfile.read(n), "ctype": self.headers["Content-Type"],
                          "token": self.headers.get("X-Admin-Token", "")}
        self._json(202, {"id": "vid-0823-1652", "status": "uploaded"})

    def do_GET(self):
        self._json(200, _Stub.status_seq.pop(0) if _Stub.status_seq else {"ingest_status": "ready"})

    def _json(self, code, payload):
        b = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


@pytest.fixture
def stub():
    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_upload_streams_every_part_and_returns_the_new_lecture_id(tmp_path, stub):
    d = _out(tmp_path)
    res = upload(d, stub, token="tok")
    assert res["id"] == "vid-0823-1652"
    body = _Stub.received["body"]
    # 서버가 Content-Length 만큼 끊김 없이 읽어냈다는 것 자체가 계산이 맞다는 증거다
    # (모자라면 rfile.read 가 멈추고, 넘치면 다음 요청 파싱이 깨진다). 계산 회귀도 함께 잠근다.
    boundary = _Stub.received["ctype"].split("boundary=")[1]
    assert len(body) == multipart_plan(parts_for(d), boundary)[2]
    for needle in (b'name="lecture_json"', b'name="original"', b"ORIGINAL", b"EDITED", b'name="thumbs_zip"'):
        assert needle in body
    assert _Stub.received["token"] == "tok"


def test_upload_omits_the_token_header_when_there_is_none(tmp_path, stub):
    upload(_out(tmp_path), stub)
    assert _Stub.received["token"] == ""


def test_wait_ready_reports_failure_instead_of_spinning(stub):
    _Stub.status_seq = [{"ingest_status": "failed", "ingest_error": "boom"}]
    with pytest.raises(RuntimeError, match="boom"):
        wait_ready(stub, "vid-0823-1652", timeout=5)


def test_wait_ready_returns_the_final_status(stub):
    _Stub.status_seq = [{"ingest_status": "ready", "embed_done": 3, "embed_total": 3}]
    assert wait_ready(stub, "vid-0823-1652", timeout=5)["embed_done"] == 3
