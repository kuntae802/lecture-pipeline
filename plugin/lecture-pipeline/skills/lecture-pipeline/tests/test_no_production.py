"""테스트 격리 가드 자체를 잠근다 — 가드가 빠지면 운영 뷰어에 가짜 작업 카드가 다시 쌓인다."""
import http.client
from urllib.parse import urlsplit

import pytest

from lecture_pipeline import config, jobs


def test_tests_run_against_a_dead_local_api():
    assert config.api() == "http://127.0.0.1:1"


def test_opening_a_connection_to_the_production_viewer_fails_the_test():
    with pytest.raises(AssertionError, match="운영 뷰어"):
        # 운영 호스트는 기본 주소에서 뽑는다 — 주소를 옮겨도 이 가드가 옛 호스트를 지키고 있지 않게.
        http.client.HTTPSConnection(urlsplit(config.DEFAULT_API).hostname, 443)


def test_progress_report_during_tests_goes_nowhere(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    jobs.start("abcdefghijk", "https://youtu.be/abcdefghijk")
    jobs.report("fetch", "running")  # 닫힌 포트라 조용히 실패해야 한다(예외 없이)
