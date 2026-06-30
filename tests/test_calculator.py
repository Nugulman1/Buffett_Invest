"""
calculator.py 순수함수 회귀 안전망 (T1).

원칙:
- tax_rate·equity_risk_premium은 명시 인자로 넘겨 settings 의존 제거(결정적).
- 현재 동작을 캡처(characterization)하되, 부채비율만 '정답 스펙'으로 작성하고
  xfail(strict)로 표시 → T4가 역수를 고치면 xpass로 빨개져 플래그 해제 신호가 된다.
"""
import pytest

from apps.models import YearlyFinancialDataObject
from apps.service.calculator import IndicatorCalculator as C


def make_year(year=2024, **kw):
    y = YearlyFinancialDataObject(year)
    for k, v in kw.items():
        setattr(y, k, v)
    return y


# ── FCF = CFO - |유형취득 + 무형취득| ────────────────────
class TestFcf:
    def test_basic(self):
        y = make_year(cfo=1000, tangible_asset_acquisition=300, intangible_asset_acquisition=100)
        assert C.calculate_fcf(y) == 600

    def test_capex_abs(self):
        # 음수 취득(처분)도 절대값 처리
        y = make_year(cfo=1000, tangible_asset_acquisition=-200, intangible_asset_acquisition=0)
        assert C.calculate_fcf(y) == 800


# ── ROIC = OI*(1-t) / (equity + debt - cash) ─────────────
class TestRoic:
    def test_basic(self):
        y = make_year(operating_income=1000, equity=4000,
                      interest_bearing_debt=2000, cash_and_cash_equivalents=1000)
        # 분자 750, 분모 5000 → 0.15
        assert C.calculate_roic(y, tax_rate=0.25) == pytest.approx(0.15)

    def test_denominator_zero_returns_zero(self):
        y = make_year(operating_income=1000, equity=1000,
                      interest_bearing_debt=0, cash_and_cash_equivalents=1000)
        assert C.calculate_roic(y, tax_rate=0.25) == 0.0

    def test_cash_none_treated_as_zero(self):
        y = make_year(operating_income=1000, equity=4000,
                      interest_bearing_debt=0, cash_and_cash_equivalents=None)
        # 분모 4000, 분자 750 → 0.1875
        assert C.calculate_roic(y, tax_rate=0.25) == pytest.approx(0.1875)


# ── IC = equity + debt - cash ────────────────────────────
class TestInvestedCapital:
    def test_basic(self):
        y = make_year(equity=4000, interest_bearing_debt=2000, cash_and_cash_equivalents=1000)
        assert C.calculate_invested_capital(y) == 5000

    def test_cash_none(self):
        y = make_year(equity=4000, interest_bearing_debt=2000, cash_and_cash_equivalents=None)
        assert C.calculate_invested_capital(y) == 6000


# ── EV = 시총 + 부채 - 현금(전액) + 비지배지분 ──────────────
class TestEv:
    def test_basic(self):
        # 현금 전액 차감(T5): 10000 + 2000 - 1000 + 500 = 11500
        assert C.calculate_ev(market_cap=10000, interest_bearing_debt=2000,
                              cash=1000, noncontrolling_interest=500) == 11500

    def test_nci_default_zero(self):
        assert C.calculate_ev(market_cap=10000, interest_bearing_debt=0, cash=0) == 10000

    def test_full_cash_subtracted(self):
        # 매직 0.7 제거 확인: 현금 전액만큼 빠짐
        assert C.calculate_ev(market_cap=5000, interest_bearing_debt=0, cash=1000) == 4000


# ── compute_ic_ev: IC/EV 단일 함수(T7) ───────────────────
class TestComputeIcEv:
    def test_with_market_cap(self):
        # IC = 4000+2000-1000 = 5000, EV = 10000+2000-1000+500 = 11500
        y = make_year(equity=4000, interest_bearing_debt=2000,
                      cash_and_cash_equivalents=1000, noncontrolling_interest=500)
        ic, ev = C.compute_ic_ev(y, market_cap=10000)
        assert ic == 5000
        assert ev == 11500

    def test_market_cap_none_ev_none(self):
        # market_cap 없으면 EV=None, IC는 계산
        y = make_year(equity=4000, interest_bearing_debt=2000, cash_and_cash_equivalents=1000)
        ic, ev = C.compute_ic_ev(y, market_cap=None)
        assert ic == 5000
        assert ev is None

    def test_matches_individual_functions(self):
        # 단일 함수가 개별 함수 조합과 동일한 결과 (drift 방지 보증)
        y = make_year(equity=7000, interest_bearing_debt=3000,
                      cash_and_cash_equivalents=500, noncontrolling_interest=200)
        ic, ev = C.compute_ic_ev(y, market_cap=20000)
        assert ic == C.calculate_invested_capital(y)
        assert ev == C.calculate_ev(20000, y.interest_bearing_debt,
                                    y.cash_and_cash_equivalents, y.noncontrolling_interest)


# ── WACC = ew*Re + dw*Rd*(1-t), Re=(bond+0.5+erp)/100 ────
class TestWacc:
    def test_basic(self):
        y = make_year(equity=6000, interest_bearing_debt=4000, interest_expense=200)
        # ew=0.6, dw=0.4, Re=(3.5+0.5+10)/100=0.14, Rd=200/4000=0.05
        # wacc = 0.6*0.14 + 0.4*0.05*0.75 = 0.084 + 0.015 = 0.099
        assert C.calculate_wacc(y, bond_yield=3.5, tax_rate=0.25,
                                equity_risk_premium=10.0) == pytest.approx(0.099)

    def test_total_capital_zero_returns_zero(self):
        y = make_year(equity=0, interest_bearing_debt=0, interest_expense=0)
        assert C.calculate_wacc(y, bond_yield=3.5, tax_rate=0.25, equity_risk_premium=10.0) == 0.0

    def test_no_debt_is_pure_cost_of_equity(self):
        y = make_year(equity=5000, interest_bearing_debt=0, interest_expense=0)
        # dw=0 → wacc = Re = 0.14
        assert C.calculate_wacc(y, bond_yield=3.5, tax_rate=0.25,
                                equity_risk_premium=10.0) == pytest.approx(0.14)


# ── 영업이익률 = OI / 매출 (소수) ─────────────────────────
class TestOperatingMargin:
    def test_basic(self):
        y = make_year(revenue=1000, operating_income=150)
        assert C.calculate_operating_margin(y) == pytest.approx(0.15)

    def test_revenue_zero_or_none_returns_none(self):
        assert C.calculate_operating_margin(make_year(revenue=0, operating_income=100)) is None
        assert C.calculate_operating_margin(make_year(revenue=None, operating_income=100)) is None

    def test_operating_income_none_returns_none(self):
        assert C.calculate_operating_margin(make_year(revenue=1000, operating_income=None)) is None


# ── equity ≡ total_equity property 통합 (T8) ──────────────
class TestEquityProperty:
    def test_equity_aliases_total_equity(self):
        assert make_year(total_equity=4000).equity == 4000

    def test_setting_equity_sets_total_equity(self):
        y = make_year()
        y.equity = 5000
        assert y.total_equity == 5000

    def test_total_equity_only_object_computes_roic(self):
        # DB 로드 시나리오(total_equity만 채움)도 ROIC가 0이 되지 않음 — T8 잠재버그 봉인
        y = make_year(total_equity=4000, operating_income=1000,
                      interest_bearing_debt=2000, cash_and_cash_equivalents=1000)
        assert C.calculate_roic(y, tax_rate=0.25) == pytest.approx(0.15)


# ── 부채비율: 표준 = 부채총계 / 자본총계 (T4 정정 완료) ────
class TestDebtRatio:
    def test_standard_formula_liabilities_over_equity(self):
        # 표준 부채비율 = 부채총계 / 자본총계 = 2000/4000 = 0.5
        y = make_year(total_equity=4000, total_liabilities=2000)
        assert C.calculate_debt_ratio(y) == pytest.approx(0.5)

    def test_no_debt_returns_zero(self):
        # 부채 0(무차입)은 유효한 0.0
        assert C.calculate_debt_ratio(make_year(total_equity=4000, total_liabilities=0)) == 0.0

    def test_liabilities_none_returns_none(self):
        assert C.calculate_debt_ratio(make_year(total_equity=4000, total_liabilities=None)) is None

    def test_equity_none_returns_none(self):
        assert C.calculate_debt_ratio(make_year(total_equity=None, total_liabilities=2000)) is None

    def test_equity_nonpositive_returns_none(self):
        # 자본잠식(자본총계 ≤ 0)이면 None
        assert C.calculate_debt_ratio(make_year(total_equity=0, total_liabilities=2000)) is None
        assert C.calculate_debt_ratio(make_year(total_equity=-100, total_liabilities=2000)) is None
