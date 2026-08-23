"""사람이 번호를 정하지 않는 id 생성. 강의 id 와 작업(job) id 가 같은 형식을 쓴다.

`<밑동>-<MMDD-HHMM>` — 밑동은 보통 유튜브 video id 다. 화면에서 어느 영상인지 바로 읽히고,
같은 영상을 여러 번 돌린 것도 시각으로 구분된다. 뷰어의 id 규칙(영숫자·`-`·`_`, 32자 이내)을
넘지 않게 밑동은 20자로 자른다.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def stamped_id(base: str | None, now: datetime | None = None) -> str:
    b = re.sub(r"[^A-Za-z0-9_-]", "", str(base or ""))[:20] or "lecture"
    return f"{b}-{(now or datetime.now(KST)):%m%d-%H%M}"
