"""테스트가 어디서 실행되든 스킬의 scripts/ 를 import 경로에 넣는다(설치 불요).

**테스트는 운영 뷰어에 절대 닿지 않는다.** 진행도 보고(jobs.report)는 VCU_API 가 없으면 내장 기본값
(운영 뷰어)으로 가므로, fetch 처럼 보고를 부르는 코드를 테스트하면 가짜 작업 카드가 운영 화면에
쌓인다(2026-09-28 실제 발생 — abcdefghijk-* 카드 22건). 그래서 모든 테스트에서 VCU_API 를 닫힌
로컬 포트로 돌리고, 그래도 운영 호스트로 연결을 열면 테스트를 실패시킨다.
스텁 서버가 필요한 테스트는 지금처럼 monkeypatch.setenv("VCU_API", stub) 로 덮으면 된다.
"""
import http.client
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lecture_pipeline import config  # noqa: E402

DEAD_API = "http://127.0.0.1:1"
PRODUCTION_HOST = urlsplit(config.DEFAULT_API).hostname


@pytest.fixture(autouse=True)
def _never_reach_the_production_viewer(monkeypatch):
    monkeypatch.setenv("VCU_API", DEAD_API)
    for cls in (http.client.HTTPConnection, http.client.HTTPSConnection):
        original = cls.__init__

        def guarded(self, host, *args, _original=original, **kwargs):
            if host == PRODUCTION_HOST:
                raise AssertionError(f"테스트가 운영 뷰어({host})에 연결하려 했다")
            _original(self, host, *args, **kwargs)

        monkeypatch.setattr(cls, "__init__", guarded)
