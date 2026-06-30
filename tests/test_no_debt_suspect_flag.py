"""
무차입 의심(셀트리온형 전수 미포착) 회사단위 판정 RED 박제.

설계 의도(기준 출처 = 사용자 요청 본문):
  기존 가드는 '연도별'(calculator.compute_ic_ev: 그 해 이자부채 0/None이면 IC/EV None)만
  존재한다. 이번엔 '모든(≥1개) 연도의 이자부채가 0 또는 None'인 **회사 단위** 무차입 의심을
  판정하는 함수를 신설한다.
    - 모든 연도 이자부채가 0/None  → flag=True (무차입 의심)
    - 양수가 한 연도라도 있으면     → flag=False
    - 한 연도도 데이터가 없으면     → flag=False (판정 불가)

추론한 인터페이스(소스 단서 + 요청 본문에서 추론):
  대상1: IndicatorCalculator.flag_no_debt_suspect(yearly_data) -> tuple[bool, str]  (staticmethod)
         yearly_data = .interest_bearing_debt 속성을 노출하는 레코드의 iterable.
  대상2: CompanyFilter.evaluate_second_filter(corp_code: str) -> dict  (staticmethod)
         반환 키 'passed'(bool, 기존 check_second_filter와 동일), 'no_debt_suspect'(bool), 'reason'(str).

구현 전 RED 사유: flag_no_debt_suspect / evaluate_second_filter 함수가 아직 미존재
  → AttributeError(클래스에 해당 staticmethod 없음)로 실패해야 정상.

기대값 출처: 모두 위 설계 의도에서 직접 도출. 코드 출력 베끼지 않음.
reason 문자열의 정확한 문구는 박제하지 않음(brittle) — bool은 정확히, reason은
'비어있지 않음' + 핵심 substring만 약하게 단언.
"""
import pytest
from types import SimpleNamespace

from apps.service.calculator import IndicatorCalculator


def _rec(debt):
    """이자부채만 노출하는 더미 연간 레코드(DB 불필요)."""
    return SimpleNamespace(interest_bearing_debt=debt)


def _records(debts):
    return [_rec(d) for d in debts]


# ── 대상1: 순수 판정 함수 ─────────────────────────────────
class TestFlagNoDebtSuspect:
    @pytest.mark.parametrize("debts, expected_flag", [
        ([0, 0, 0], True),            # 전부0 → 무차입 의심
        ([None, None], True),         # 전부None → 무차입 의심
        ([0, None, 0], True),         # 0·None 혼합(무차입쪽) → 의심
        ([0, 20000, None], False),    # 양수 존재 → 의심 아님
        ([100, 200], False),          # 전부양수 → 의심 아님
        ([], False),                  # 빈 데이터 → 판정 불가
        ([0], True),                  # 단일연도 0 → 의심
        ([None], True),               # 단일연도 None → 의심
        ([500], False),               # 단일연도 양수 → 의심 아님
    ])
    def test_flag_value(self, debts, expected_flag):
        # 기대값 출처: 의도 "모든 연도 0/None이면 True, 양수 있으면 False, 데이터 없으면 False"
        flag, reason = IndicatorCalculator.flag_no_debt_suspect(_records(debts))
        assert flag is expected_flag

    @pytest.mark.parametrize("debts", [
        [0, 0, 0], [None, None], [0, None, 0],
        [0, 20000, None], [100, 200], [0], [None], [500],
    ])
    def test_reason_not_empty_when_has_data(self, debts):
        # 데이터가 있으면 reason은 비어있지 않아야(사유 노출)
        _, reason = IndicatorCalculator.flag_no_debt_suspect(_records(debts))
        assert isinstance(reason, str) and reason.strip() != ""

    def test_reason_substring_when_suspect(self):
        # 무차입 의심(전부0) reason엔 '무차입' 또는 '이자부채' 핵심 substring 포함
        _, reason = IndicatorCalculator.flag_no_debt_suspect(_records([0, 0, 0]))
        assert ("무차입" in reason) or ("이자부채" in reason)

    def test_reason_mentions_data_when_empty(self):
        # 빈 데이터 → 판정불가 취지가 reason에 '데이터'로 드러나야
        flag, reason = IndicatorCalculator.flag_no_debt_suspect(_records([]))
        assert flag is False
        assert "데이터" in reason

    @pytest.mark.parametrize("debts", [[0], [None]])
    def test_reason_hints_single_year_count(self, debts):
        # 단일연도(N=1) 케이스: flag=True지만 사유에 연도수 단서가 들어가야(신뢰도 약함 표시)
        flag, reason = IndicatorCalculator.flag_no_debt_suspect(_records(debts))
        assert flag is True
        assert ("1" in reason) or ("단일" in reason)


# ── 대상2: 2차 필터 surface (DB 연동) ─────────────────────
@pytest.mark.django_db
class TestEvaluateSecondFilter:
    def _make_db_company(self, corp_code, rows):
        """rows: [(year, interest_bearing_debt, roic, wacc), ...]"""
        from apps.models import Company, YearlyFinancialData
        company = Company.objects.create(corp_code=corp_code, company_name="T")
        for year, debt, roic, wacc in rows:
            YearlyFinancialData.objects.create(
                company=company, year=year,
                interest_bearing_debt=debt, roic=roic, wacc=wacc,
            )
        return corp_code

    def test_no_debt_company_flagged_passed_unchanged(self):
        from apps.service.filter import CompanyFilter
        # 모든 연도 이자부채 0/None, spread 통과(roic0.10 - wacc0.05 = 0.05 ≥ 0.02)
        code = self._make_db_company("00000011", [
            (2024, 0, 0.10, 0.05),
            (2023, None, 0.10, 0.05),
            (2022, 0, 0.10, 0.05),
        ])
        result = CompanyFilter.evaluate_second_filter(code)
        assert result["no_debt_suspect"] is True                       # 모든 연도 0/None
        assert isinstance(result["reason"], str) and result["reason"].strip() != ""
        # 무차입 의심이어도 통과/탈락은 기존 판정과 동일(자동으로 안 바뀜)
        assert result["passed"] == CompanyFilter.check_second_filter(code)

    def test_normal_company_not_flagged_passed_unchanged(self):
        from apps.service.filter import CompanyFilter
        # 모든 연도 이자부채>0 → 무차입 의심 아님
        code = self._make_db_company("00000012", [
            (2024, 20_000_000_000, 0.10, 0.05),
            (2023, 18_000_000_000, 0.10, 0.05),
            (2022, 15_000_000_000, 0.10, 0.05),
        ])
        result = CompanyFilter.evaluate_second_filter(code)
        assert result["no_debt_suspect"] is False                      # 양수 존재
        assert result["passed"] == CompanyFilter.check_second_filter(code)
