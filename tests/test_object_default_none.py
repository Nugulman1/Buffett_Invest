"""
RED 박제 (방향 B / 대상 1): YearlyFinancialDataObject 의 미계산 지표 기본값을 None으로 통일.

추론한 인터페이스: apps.models.YearlyFinancialDataObject(year) — year 위치/키워드 인자.
현재(models.py 339~341): self.fcf=0, self.roic=0.0, self.wacc=0.0
합격조건: 새로 만든 객체의 .roic / .wacc / .fcf 가 모두 None.
주의: roic/wacc/fcf 3개만 검증한다. total_equity 등 다른 기본값은 건드리지 않으므로 테스트하지 않는다.
"""
from apps.models import YearlyFinancialDataObject


def test_roic_default_is_none():
    # 출처: 사용자 합격조건 대상 1 — 미계산 roic 기본값 None
    yd = YearlyFinancialDataObject(year=2024)
    assert yd.roic is None


def test_wacc_default_is_none():
    # 출처: 사용자 합격조건 대상 1 — 미계산 wacc 기본값 None
    yd = YearlyFinancialDataObject(year=2024)
    assert yd.wacc is None


def test_fcf_default_is_none():
    # 출처: 사용자 합격조건 대상 1 — 미계산 fcf 기본값 None
    yd = YearlyFinancialDataObject(year=2024)
    assert yd.fcf is None
