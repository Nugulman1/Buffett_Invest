"""
내재가치 핵심지표 신규 6함수 RED 박제 (구현 전).

원칙:
- 대상 함수는 아직 calculator.py에 없음 → C.<func> 접근에서 AttributeError로 RED.
- 모든 기대값은 손계산하여 주석에 산식을 남긴다(구현을 돌려 베끼지 않음).
- 순수함수 컨벤션: make_year(setattr) 로 객체 조립 후 정적메서드 직접 호출.
"""
import math

import pytest

from apps.models import YearlyFinancialDataObject
from apps.service.calculator import IndicatorCalculator as C


def make_year(year=2024, **kw):
    y = YearlyFinancialDataObject(year)
    for k, v in kw.items():
        setattr(y, k, v)
    return y


# ── 1) g = ROIC × 유보율(b), b = 1 − 배당성향, 배당성향 = dividend_paid/net_income ──
# 예상 시그니처: C.calculate_g(yearly_data) -> float | None
class TestCalculateG:
    def test_basic(self):
        # payout = 300/1000 = 0.3, b = 1-0.3 = 0.7, g = 0.15*0.7 = 0.105
        y = make_year(roic=0.15, net_income=1000, dividend_paid=300)
        assert C.calculate_g(y) == pytest.approx(0.105)

    def test_dividend_none_payout_zero_b_one(self):
        # dividend_paid None → 배당성향 0 → b=1.0 → g = roic = 0.15
        y = make_year(roic=0.15, net_income=1000, dividend_paid=None)
        assert C.calculate_g(y) == pytest.approx(0.15)

    def test_net_income_nonpositive_returns_none(self):
        # net_income ≤ 0 → 배당성향 정의 불가 → None
        y = make_year(roic=0.15, net_income=-100, dividend_paid=300)
        assert C.calculate_g(y) is None

    def test_net_income_zero_returns_none(self):
        y = make_year(roic=0.15, net_income=0, dividend_paid=0)
        assert C.calculate_g(y) is None

    def test_roic_none_returns_none(self):
        y = make_year(roic=None, net_income=1000, dividend_paid=300)
        assert C.calculate_g(y) is None

    def test_dividend_gt_income_b_clamped_zero(self):
        # payout = 1500/1000 = 1.5 → b = -0.5 → clamp 0 → g = 0.15*0 = 0.0
        y = make_year(roic=0.15, net_income=1000, dividend_paid=1500)
        assert C.calculate_g(y) == pytest.approx(0.0)

    def test_dividend_negative_b_clamped_one(self):
        # payout = -200/1000 = -0.2 → b = 1.2 → clamp 1.0 → g = roic = 0.15
        y = make_year(roic=0.15, net_income=1000, dividend_paid=-200)
        assert C.calculate_g(y) == pytest.approx(0.15)


# ── 2) Altman Z''-Score (1995) ───────────────────────────────────
# Z'' = 3.25 + 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4
# 예상 시그니처: C.calculate_altman_z_double_prime(yearly_data) -> float | None
class TestAltmanZDoublePrime:
    def _full(self, **over):
        base = dict(
            total_assets=10000,
            current_assets=5000,
            current_liabilities=3000,
            retained_earnings=2000,
            operating_income=1500,
            total_equity=6000,
            total_liabilities=4000,
        )
        base.update(over)
        return make_year(**base)

    def test_basic(self):
        # X1=(5000-3000)/10000=0.2, X2=2000/10000=0.2, X3=1500/10000=0.15, X4=6000/4000=1.5
        # Z'' = 3.25 + 6.56*0.2 + 3.26*0.2 + 6.72*0.15 + 1.05*1.5
        #     = 3.25 + 1.312 + 0.652 + 1.008 + 1.575 = 7.797
        assert C.calculate_altman_z_double_prime(self._full()) == pytest.approx(7.797)

    def test_total_assets_none_returns_none(self):
        assert C.calculate_altman_z_double_prime(self._full(total_assets=None)) is None

    def test_total_assets_zero_returns_none(self):
        assert C.calculate_altman_z_double_prime(self._full(total_assets=0)) is None

    def test_total_liabilities_none_returns_none(self):
        assert C.calculate_altman_z_double_prime(self._full(total_liabilities=None)) is None

    def test_total_liabilities_zero_returns_none(self):
        assert C.calculate_altman_z_double_prime(self._full(total_liabilities=0)) is None

    @pytest.mark.parametrize(
        "field",
        ["current_assets", "current_liabilities", "retained_earnings",
         "operating_income", "total_equity"],
    )
    def test_required_field_none_returns_none(self, field):
        assert C.calculate_altman_z_double_prime(self._full(**{field: None})) is None


# ── 3) Zmijewski (1984) 부실확률 ─────────────────────────────────
# X = −4.336 − 4.513·X1 + 5.679·X2 + 0.004·X3 ; P = 1/(1+e^(−X))
# 예상 시그니처: C.calculate_zmijewski(yearly_data) -> float | None
class TestZmijewski:
    def _full(self, **over):
        base = dict(
            total_assets=10000,
            net_income=500,
            total_liabilities=7000,
            current_assets=3000,
            current_liabilities=2000,
        )
        base.update(over)
        return make_year(**base)

    def test_basic(self):
        # X1=ROA=500/10000=0.05, X2=7000/10000=0.7, X3=3000/2000=1.5
        # X = -4.336 - 4.513*0.05 + 5.679*0.7 + 0.004*1.5
        #   = -4.336 - 0.22565 + 3.9753 + 0.006 = -0.58035
        # P = 1/(1+e^(-(-0.58035))) = 1/(1+e^0.58035) ≈ 0.358851
        X = -0.58035  # 손계산값(입력에서만 도출, 구현 독립)
        expected = 1.0 / (1.0 + math.exp(-X))
        assert C.calculate_zmijewski(self._full()) == pytest.approx(expected, abs=1e-6)

    def test_high_distress_prob_over_half(self):
        # 적자+고부채 → 부실확률 > 0.5
        # X1=ROA=-2000/10000=-0.2, X2=9500/10000=0.95, X3=1000/3000=0.33333
        # X = -4.336 - 4.513*(-0.2) + 5.679*0.95 + 0.004*0.33333
        #   = -4.336 + 0.9026 + 5.39505 + 0.0013333 = 1.962983
        # P = 1/(1+e^-1.962983) ≈ 0.8768 (>0.5)
        y = self._full(net_income=-2000, total_liabilities=9500,
                       current_assets=1000, current_liabilities=3000)
        assert C.calculate_zmijewski(y) > 0.5

    def test_total_assets_none_returns_none(self):
        assert C.calculate_zmijewski(self._full(total_assets=None)) is None

    def test_total_assets_zero_returns_none(self):
        assert C.calculate_zmijewski(self._full(total_assets=0)) is None

    def test_net_income_none_returns_none(self):
        assert C.calculate_zmijewski(self._full(net_income=None)) is None

    def test_total_liabilities_none_returns_none(self):
        assert C.calculate_zmijewski(self._full(total_liabilities=None)) is None

    def test_current_assets_none_returns_none(self):
        assert C.calculate_zmijewski(self._full(current_assets=None)) is None

    def test_current_liabilities_none_returns_none(self):
        assert C.calculate_zmijewski(self._full(current_liabilities=None)) is None

    def test_current_liabilities_zero_returns_none(self):
        assert C.calculate_zmijewski(self._full(current_liabilities=0)) is None


# ── 4) classify_altman_z: None→None; ≥2.6 safe; 1.1≤z<2.6 grey; <1.1 distress ──
# 예상 시그니처: C.classify_altman_z(z: float | None) -> str | None
class TestClassifyAltmanZ:
    def test_none(self):
        assert C.classify_altman_z(None) is None

    @pytest.mark.parametrize(
        "z, expected",
        [
            (2.6, "safe"),     # 경계: 2.6 포함 → safe
            (3.0, "safe"),
            (2.59, "grey"),    # 경계 바로 아래
            (1.1, "grey"),     # 경계: 1.1 포함 → grey
            (1.09, "distress"),# 경계 바로 아래
            (0.0, "distress"),
        ],
    )
    def test_thresholds(self, z, expected):
        assert C.classify_altman_z(z) == expected


# ── 5) flag_zmijewski: None→None; ≥0.5 True(부실); else False ─────
# 예상 시그니처: C.flag_zmijewski(prob: float | None) -> bool | None
class TestFlagZmijewski:
    def test_none(self):
        assert C.flag_zmijewski(None) is None

    @pytest.mark.parametrize(
        "prob, expected",
        [
            (0.5, True),    # 경계 0.5 → True
            (0.7, True),
            (0.49, False),
            (0.0, False),
        ],
    )
    def test_threshold(self, prob, expected):
        assert C.flag_zmijewski(prob) is expected


# ── 6) flag_fcf_negative: 최근 lookback개 중 non-None fcf에서 음수 ≥ min_negative ──
# 예상 시그니처: C.flag_fcf_negative(yearly_data_list, lookback=3, min_negative=2) -> (bool, str)
class TestFlagFcfNegative:
    def _recs(self, pairs):
        # pairs: [(year, fcf), ...]
        return [make_year(year=y, fcf=f) for y, f in pairs]

    def test_two_negatives_true(self):
        # 최근3년 [-10,-20,30] → 음수 2개 ≥ 2 → True
        recs = self._recs([(2024, -10), (2023, -20), (2022, 30)])
        ok, reason = C.flag_fcf_negative(recs)
        assert ok is True
        assert reason  # 사유 truthy

    def test_one_negative_false(self):
        # 최근3년 [-10,30,40] → 음수 1개 < 2 → False
        recs = self._recs([(2024, -10), (2023, 30), (2022, 40)])
        ok, reason = C.flag_fcf_negative(recs)
        assert ok is False
        assert reason

    def test_none_excluded_then_judged_true(self):
        # 최근3년 = 2024:None, 2023:-10, 2022:-20 → None 제외 후 음수 2개 → True
        recs = self._recs([(2024, None), (2023, -10), (2022, -20), (2021, 30)])
        ok, reason = C.flag_fcf_negative(recs)
        assert ok is True
        assert reason

    def test_empty_list_false(self):
        ok, reason = C.flag_fcf_negative([])
        assert ok is False
        assert reason  # 데이터없음 취지 사유

    def test_all_none_window_false(self):
        # 유효 fcf 0개 → False
        recs = self._recs([(2024, None), (2023, None), (2022, None)])
        ok, reason = C.flag_fcf_negative(recs)
        assert ok is False
        assert reason
