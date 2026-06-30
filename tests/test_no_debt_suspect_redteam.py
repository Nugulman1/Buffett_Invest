"""레드팀 재현 결함의 회귀 박제 (메인 판정 후 작성·교정).

기대값 출처: 아젠다 의도 + 파이프라인 진실에서 직접 도출(구현 출력 베끼지 않음).

파이프라인 진실(핵심): orchestrator.py:184-186 이 '이자부채 0/None ⟹ roic/wacc=None' 을 강제하며
roic/wacc 의 유일한 산출 경로다. 따라서 check_second_filter 의 valid 윈도우(roic·wacc not-None)는
**구조적으로 부채>0 행들뿐**이다. surface 의 이자부채 윈도우를 valid 로 맞추면 부채0/None 행을
영원히 못 봐서 no_debt_suspect=True 가 실데이터에서 도달 불가가 된다(기능 사망). 그러므로 surface
윈도우는 valid 가 아니라 **raw 최근3년 이자부채**여야 한다(DEC-6).

[2] 음수 이자부채 사유 정확성(순수함수): 양수가 0개인데 사유가 '양수 있음'을 주장하면 안 된다.
"""
from types import SimpleNamespace

import pytest

from apps.models import Company, YearlyFinancialData
from apps.service.calculator import IndicatorCalculator as IC
from apps.service.filter import CompanyFilter


def _make(corp, rows):
    """rows: [(year, interest_bearing_debt, roic, wacc)] — 커플링 준수해서 호출자가 구성."""
    c = Company.objects.create(corp_code=corp, company_name=corp)
    for y, d, roic, wacc in rows:
        YearlyFinancialData.objects.create(
            company=c, year=y, interest_bearing_debt=d, roic=roic, wacc=wacc
        )
    return c


# ---- [2] 사유 정확성 (순수함수) ----

def test_negative_only_reason_does_not_claim_positive():
    """음수만(양수 0개): flag=False 지만 사유가 '양수 있음'을 거짓 주장하지 않는다."""
    flag, reason = IC.flag_no_debt_suspect(
        [SimpleNamespace(interest_bearing_debt=d) for d in [0, 0, -100]]
    )
    assert flag is False
    assert "양수" not in reason, f"양수 0개인데 사유가 '양수' 주장: {reason!r}"
    assert reason


def test_all_negative_reason_does_not_claim_positive():
    flag, reason = IC.flag_no_debt_suspect(
        [SimpleNamespace(interest_bearing_debt=d) for d in [-50, -60]]
    )
    assert flag is False
    assert "양수" not in reason, f"양수 0개인데 사유가 '양수' 주장: {reason!r}"


# ---- [1] surface 윈도우 = raw 최근3년 (커플링 준수 실데이터) ----

@pytest.mark.django_db
def test_real_celltrion_all_no_debt_is_surfaced():
    """진짜 셀트리온형: 최근3년 전부 무차입 ⟹ roic/wacc 전부 None(커플링).
    check_second_filter 는 유효데이터 없음으로 passed=False(탈락)지만, 그 탈락은 '무차입 정책 탓'이다.
    → no_debt_suspect=True 로 surface 돼야(근거 없는 탈락 노출). 이게 기능의 존재 목적."""
    _make("B0000001", [(2024, 0, None, None), (2023, 0, None, None), (2022, None, None, None)])
    res = CompanyFilter.evaluate_second_filter("B0000001")
    assert res["passed"] == CompanyFilter.check_second_filter("B0000001")
    assert res["passed"] is False, "전부 무차입이면 valid 데이터 없어 탈락(전제 확인)"
    assert res["no_debt_suspect"] is True, (
        "최근3년 전부 무차입이면 탈락이 무차입 정책 탓이므로 surface 돼야"
    )
    assert res["reason"]


@pytest.mark.django_db
def test_real_normal_company_not_suspect():
    """정상(차입 있음): 최근3년 부채>0 ⟹ roic/wacc 존재 → 의심 아님."""
    _make("B0000002", [
        (2024, 8_000_000_000, 0.10, 0.05),
        (2023, 7_000_000_000, 0.10, 0.05),
        (2022, 6_000_000_000, 0.10, 0.05),
    ])
    res = CompanyFilter.evaluate_second_filter("B0000002")
    assert res["passed"] == CompanyFilter.check_second_filter("B0000002")
    assert res["no_debt_suspect"] is False, "최근3년 차입 정상이면 의심 아님"


@pytest.mark.django_db
def test_real_mixed_recent_window_has_debt_not_suspect():
    """혼합(실데이터): 최근3년에 부채>0 연도가 섞여 있으면(=진짜 무차입 아님) 의심 아님.
    부채0 연도는 roic/wacc None 이라 통과결정엔 안 쓰이지만, surface 는 raw 윈도우라 부채>0 을 본다."""
    _make("B0000003", [
        (2024, 9_000_000_000, 0.10, 0.05),   # 부채>0 → roic 존재
        (2023, 0, None, None),               # 부채0 → roic None
        (2022, 5_000_000_000, 0.10, 0.05),   # 부채>0 → roic 존재
    ])
    res = CompanyFilter.evaluate_second_filter("B0000003")
    assert res["passed"] == CompanyFilter.check_second_filter("B0000003")
    assert res["no_debt_suspect"] is False, "최근3년에 차입 연도가 있으면 무차입 의심 아님"


@pytest.mark.django_db
def test_window_is_recent_three_not_all_years():
    """윈도우는 '최근 3년' (전 연도 아님): 최근3년 전부 무차입이면, 그보다 옛 연도에 차입이
    있더라도 no_debt_suspect=True. (전 연도 기준이면 옛 차입에 가려 False가 됐을 것 — 그 회귀 방지.)"""
    _make("B0000004", [
        (2024, 0, None, None),
        (2023, 0, None, None),
        (2022, None, None, None),
        (2019, 5_000_000_000, 0.10, 0.05),   # 윈도우 밖 옛 차입
    ])
    res = CompanyFilter.evaluate_second_filter("B0000004")
    assert res["passed"] == CompanyFilter.check_second_filter("B0000004")
    assert res["no_debt_suspect"] is True, (
        "최근3년이 전부 무차입이면 옛 차입연도가 있어도 의심 — 윈도우는 최근3년"
    )
