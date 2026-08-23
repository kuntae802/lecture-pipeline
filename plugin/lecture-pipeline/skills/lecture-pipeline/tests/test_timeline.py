from lecture_pipeline.timeline import edit_at, edited_duration, map_span, map_time

CUTS = [(10.0, 12.0), (20.0, 25.0)]


def test_map_time_shifts_by_preceding_cuts():
    assert map_time(5.0, CUTS) == 5.0
    assert map_time(15.0, CUTS) == 13.0
    assert map_time(30.0, CUTS) == 23.0
    assert map_time(11.0, CUTS) is None


def test_map_span_clamps_and_nulls():
    assert map_span(5.0, 8.0, CUTS) == [5.0, 8.0]
    assert map_span(10.5, 11.5, CUTS) is None            # 완전히 컷 안
    assert map_span(9.0, 11.0, CUTS) == [9.0, 10.0]      # 끝이 컷 안 → 컷 시작(편집본)으로
    assert map_span(11.0, 14.0, CUTS) == [10.0, 12.0]    # 시작이 컷 안 → 컷 시작(편집본)
    assert map_span(9.0, 26.0, CUTS) == [9.0, 19.0]      # 두 컷을 모두 건너뜀
    assert map_span(12.0, 20.0, CUTS) == [10.0, 18.0]    # 경계에 정확히 닿는 구간


def test_duration_and_edit_at():
    assert edited_duration(100.0, CUTS) == 93.0
    assert edit_at(20.0, CUTS) == 18.0
    assert edit_at(10.0, CUTS) == 10.0
