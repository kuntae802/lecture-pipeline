"""뷰어 웹 주소 한 곳.

**기본값을 코드에 박는다(2026-08-23 결정).** 뷰어가 하나뿐인 데모 단계라, 설치한 사람이
환경변수를 설정하거나 설정 파일을 만들 이유가 없다 — 설치하고 URL 만 던지면 업로드와
진행도까지 그대로 동작해야 한다.

우선순위는 `--api` 인자 > `VCU_API` 환경변수 > 이 기본값. 다른 뷰어에 올리거나 자동화에서
갈아끼울 여지는 남겨 둔다.
"""
from __future__ import annotations

import os

DEFAULT_API = "https://kuntae802.mooo.com/vcu_lecture_system_proposal/api"


def api(override: str = "") -> str:
    return (override or os.environ.get("VCU_API") or DEFAULT_API).rstrip("/")


def token(override: str = "") -> str:
    """관리자 토큰. 뷰어가 요구할 때만 쓰이고, 없으면 헤더 자체를 보내지 않는다."""
    return override or os.environ.get("VCU_API_TOKEN", "")


def is_default() -> bool:
    """기본 뷰어를 쓰고 있는지 — doctor 가 어디로 올라가는지 보여줄 때 쓴다."""
    return api() == DEFAULT_API.rstrip("/")
