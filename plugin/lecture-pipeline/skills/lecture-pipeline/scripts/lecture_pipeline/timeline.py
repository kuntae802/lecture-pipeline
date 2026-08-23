"""원본 타임라인 → 편집본 타임라인.

cuts 는 (start, end) 초의 리스트이며 겹치지 않고 정렬돼 있다고 가정한다(merge 단계가 보장).
- map_time(t): 컷 안이면 None, 아니면 t 이전에 끝난 컷 길이 합만큼 당긴 시각
- edit_at(cut_start): 컷 시작 지점이 편집본에서 놓이는 위치(= 컷 앞 keep 의 끝)
- map_span(s, e): 완전히 한 컷 안이면 None, 걸치면 컷 경계(편집본)로 클램프
- edited_duration(total): 전체 길이 − 컷 길이 합
"""
from __future__ import annotations


def _removed_before(t: float, cuts) -> float:
    return sum(e - s for s, e in cuts if e <= t)


def _containing(t: float, cuts):
    for s, e in cuts:
        if s <= t < e:
            return (s, e)
    return None


def map_time(t: float, cuts) -> float | None:
    if _containing(t, cuts):
        return None
    return round(t - _removed_before(t, cuts), 3)


def edit_at(cut_start: float, cuts) -> float:
    return round(cut_start - _removed_before(cut_start, cuts), 3)


def map_span(s: float, e: float, cuts) -> list | None:
    cs, ce = _containing(s, cuts), _containing(e, cuts)
    if cs and s >= cs[0] and e <= cs[1]:   # 구간 전체가 한 컷 안(끝 경계 포함) → 편집본에 없음
        return None
    es = edit_at(cs[0], cuts) if cs else map_time(s, cuts)
    ee = edit_at(ce[0], cuts) if ce else round(e - _removed_before(e, cuts), 3)
    return [es, ee]


def edited_duration(total: float, cuts) -> float:
    return round(total - sum(e - s for s, e in cuts), 3)
