"""진행도 보고의 계약은 두 가지다 — 작업 폴더가 job 의 경계라는 것, 그리고
보고가 어떤 이유로 실패해도 파이프라인을 막지 않는다는 것."""
import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from lecture_pipeline import config, jobs
from lecture_pipeline.ids import KST, stamped_id

AT = datetime(2026, 8, 23, 18, 30, tzinfo=KST)


def test_stamped_id_shape_and_limits():
    assert stamped_id("YO4BXrbSgpw", AT) == "YO4BXrbSgpw-0823-1830"
    assert stamped_id(None, AT) == "lecture-0823-1830"
    assert stamped_id("https://youtu.be/abc", AT) == "httpsyoutubeabc-0823-1830"
    assert len(stamped_id("x" * 60, AT)) <= 32


def test_start_opens_a_new_job_in_the_working_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    job = jobs.start("YO4BXrbSgpw", "https://youtu.be/YO4BXrbSgpw")
    assert job["job_id"].startswith("YO4BXrbSgpw-")
    assert json.loads((tmp_path / "workspace/.job").read_text())["video_id"] == "YO4BXrbSgpw"


def test_rerunning_fetch_starts_a_separate_job(tmp_path, monkeypatch):
    # 같은 영상을 다시 돌리면 새 작업이다 — 앞 작업의 진행도를 덮어쓰면 안 된다.
    monkeypatch.chdir(tmp_path)
    first = jobs.start("vid")["job_id"]
    monkeypatch.setattr(jobs, "stamped_id", lambda *a, **k: "vid-0823-1900")
    assert jobs.start("vid")["job_id"] != first


def test_two_folders_are_two_jobs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    monkeypatch.chdir(tmp_path / "a")
    jobs.start("vid")
    monkeypatch.chdir(tmp_path / "b")
    assert jobs.load() is None  # b 폴더는 아직 작업이 없다


def test_load_returns_none_without_a_job_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert jobs.load() is None


# ── 보고는 어떤 상황에서도 예외를 내지 않는다 ──────────────────────────────────
def test_viewer_is_built_in_so_a_fresh_install_needs_no_setup(monkeypatch):
    """설치만 하면 업로드·진행도가 동작해야 한다 — 환경변수 설정을 요구하지 않는다."""
    monkeypatch.delenv("VCU_API", raising=False)
    assert config.api().startswith("https://") and config.is_default()


def test_env_var_overrides_the_built_in_viewer(monkeypatch):
    monkeypatch.setenv("VCU_API", "http://other.example/api/")
    assert config.api() == "http://other.example/api" and not config.is_default()


def test_explicit_argument_beats_everything(monkeypatch):
    monkeypatch.setenv("VCU_API", "http://env.example/api")
    assert config.api("http://cli.example/api") == "http://cli.example/api"


def test_report_is_a_noop_without_a_job_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VCU_API", "http://127.0.0.1:1")
    jobs.report("fetch", "running")


def test_report_swallows_a_dead_server(tmp_path, monkeypatch):
    # 뷰어가 죽어 있어도 강의 제작은 계속 가야 한다.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VCU_API", "http://127.0.0.1:1")
    jobs.start("vid")
    jobs.report("render", "running")


class _Stub(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        _Stub.seen.append({"path": self.path, "body": json.loads(self.rfile.read(n))})
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")


@pytest.fixture
def stub():
    _Stub.seen = []
    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_report_posts_the_step_under_the_job_id(tmp_path, monkeypatch, stub):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VCU_API", stub)
    job = jobs.start("YO4BXrbSgpw", "https://youtu.be/YO4BXrbSgpw")
    jobs.report("edit", "running", "8/19")
    assert _Stub.seen[-1]["path"] == f"/jobs/{job['job_id']}"
    body = _Stub.seen[-1]["body"]
    assert (body["step"], body["status"], body["detail"]) == ("edit", "running", "8/19")
    assert body["video_id"] == "YO4BXrbSgpw"


def test_report_carries_extra_fields_like_the_finished_lecture(tmp_path, monkeypatch, stub):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VCU_API", stub)
    jobs.start("vid")
    jobs.report("upload", "running", "적재 대기", lecture_id="vid-0823-1830", title="3강")
    assert _Stub.seen[-1]["body"]["lecture_id"] == "vid-0823-1830"


def test_api_base_path_is_preserved(tmp_path, monkeypatch, stub):
    # 공개 URL 은 /vcu_lecture_system_proposal/api 처럼 하위 경로에 붙어 있다.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VCU_API", stub + "/sub/api")
    job = jobs.start("vid")
    jobs.report("fetch", "done")
    assert _Stub.seen[-1]["path"] == f"/sub/api/jobs/{job['job_id']}"


def test_steps_match_the_pipeline_order():
    assert jobs.STEPS[0] == "fetch" and jobs.STEPS[-1] == "upload"
    assert "edit" in jobs.STEPS and "render" in jobs.STEPS


def test_a_new_run_in_the_same_folder_does_not_revive_the_previous_job(tmp_path, monkeypatch, stub):
    """같은 폴더에서 다른 강의를 돌릴 때, lp.py 가 fetch 시작을 먼저 알리면 앞 작업의 .job 으로
    보고가 날아가 끝난 카드가 되살아난다. 그래서 fetch 시작 보고는 lp.py 가 하지 않는다."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VCU_API", stub)
    old = jobs.start("OLDVIDEO")["job_id"]
    jobs.report("upload", "done")            # 앞 작업 완료
    _Stub.seen.clear()

    # 새 강의: fetch 가 job 을 새로 열고 스스로 알린다
    new = jobs.start("NEWVIDEO")["job_id"]
    jobs.report("fetch", "running")
    assert new != old
    assert all(s["path"].endswith(new) for s in _Stub.seen), "앞 작업 id 로 간 보고가 있다"
