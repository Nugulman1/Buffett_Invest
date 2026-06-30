"""
RED 박제: IndicatorCalculator.fill_valuation_indicators(yd) (신설 예정, 아직 없음).

추론한 인터페이스: apps.service.calculator.IndicatorCalculator 의 staticmethod.
단일 YearlyFinancialDataObject(yd)를 받아 in-place로 5개 속성을 세팅하고 None 반환.
  yd.sustainable_growth / yd.altman_z / yd.altman_z_class / yd.zmijewski / yd.zmijewski_flag

기대값은 calculator.py docstring 공식을 손계산해 박제(calculate_* 실행출력 복사 금지).
"""
import pytest

from apps.models import YearlyFinancialDataObject
from apps.service.calculator import IndicatorCalculator as C


def make_year(year=2024, **kw):
    y = YearlyFinancialDataObject(year)
    for k, v in kw.items():
        setattr(y, k, v)
    return y


# 케이스 (a) 모든 입력 정상 → 5개 손계산 기대값
class TestFillNormal:
    def _yd(self):
        # 입력: roic 0.20, net_income 1000, dividend_paid 400,
        # total_assets 10000, total_liabilities 4000, total_equity 6000,
        # current_assets 5000, current_liabilities 2000,
        # retained_earnings 3000, operating_income 1500
        return make_year(
            roic=0.20, net_income=1000, dividend_paid=400,
            total_assets=10000, total_liabilities=4000, total_equity=6000,
            current_assets=5000, current_liabilities=2000,
            retained_earnings=3000, operating_income=1500,
        )

    def test_returns_none(self):
        # 계약: in-place 세팅, 반환값 None
        yd = self._yd()
        assert C.fill_valuation_indicators(yd) is None

    def test_sustainable_growth(self):
        yd = self._yd()
        C.fill_valuation_indicators(yd)
        # payout=400/1000=0.4, b=0.6, g=0.20*0.6=0.12 (docstring g 공식)
        assert yd.sustainable_growth == pytest.approx(0.12)

    def test_altman_z(self):
        yd = self._yd()
        C.fill_valuation_indicators(yd)
        # X1=0.3,X2=0.3,X3=0.15,X4=1.5 → 3.25+1.968+0.978+1.008+1.575=8.779
        assert yd.altman_z == pytest.approx(8.779)

    def test_altman_z_class(self):
        yd = self._yd()
        C.fill_valuation_indicators(yd)
        # 8.779 >= 2.6 → 'safe'
        assert yd.altman_z_class == "safe"

    def test_zmijewski(self):
        yd = self._yd()
        C.fill_valuation_indicators(yd)
        # X=-4.336-0.4513+2.2716+0.010=-2.5057, P=1/(1+e^2.5057)=0.0754596
        assert yd.zmijewski == pytest.approx(0.075460, abs=1e-4)

    def test_zmijewski_flag(self):
        yd = self._yd()
        C.fill_valuation_indicators(yd)
        # P=0.0754596 < 0.5 → False
        assert yd.zmijewski_flag is False


# 케이스 (b) roic=None → sustainable_growth None
class TestFillRoicNone:
    def test_growth_none(self):
        yd = make_year(
            roic=None, net_income=1000, dividend_paid=400,
            total_assets=10000, total_liabilities=4000, total_equity=6000,
            current_assets=5000, current_liabilities=2000,
            retained_earnings=3000, operating_income=1500,
        )
        C.fill_valuation_indicators(yd)
        # calculate_g: roic None → None
        assert yd.sustainable_growth is None


# 케이스 (c) total_assets=None → altman_z·class·zmijewski·flag 모두 None
class TestFillTotalAssetsNone:
    def _yd(self):
        return make_year(
            roic=0.20, net_income=1000, dividend_paid=400,
            total_assets=None, total_liabilities=4000, total_equity=6000,
            current_assets=5000, current_liabilities=2000,
            retained_earnings=3000, operating_income=1500,
        )

    def test_altman_z_none(self):
        yd = self._yd()
        C.fill_valuation_indicators(yd)
        assert yd.altman_z is None

    def test_altman_z_class_none(self):
        yd = self._yd()
        C.fill_valuation_indicators(yd)
        assert yd.altman_z_class is None

    def test_zmijewski_none(self):
        yd = self._yd()
        C.fill_valuation_indicators(yd)
        assert yd.zmijewski is None

    def test_zmijewski_flag_none(self):
        yd = self._yd()
        C.fill_valuation_indicators(yd)
        assert yd.zmijewski_flag is None
