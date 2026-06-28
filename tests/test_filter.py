"""
filter.py 회귀 안전망 (T1).

1차 필터(순수함수) + 2차 필터(check_second_filter, DB 조회)를 모두 캡처.
classify_company_size 임계값은 '실제 코드값' 기준으로 픽스처 구성:
  small < 5_000_000_000, large >= 10_000_000_000_000, 그 외 medium.
"""
import pytest

from apps.models import YearlyFinancialDataObject, CompanyFinancialObject
from apps.service.filter import CompanyFilter as F


def make_year(year, **kw):
    y = YearlyFinancialDataObject(year)
    for k, v in kw.items():
        setattr(y, k, v)
    return y


def make_company(years):
    c = CompanyFinancialObject()
    c.yearly_data = years
    return c


# ── 영업이익 필터: 최근5년 적자 ≤ 1회 ─────────────────────
class TestOperatingIncome:
    def test_all_positive_passes(self):
        c = make_company([make_year(y, operating_income=100) for y in range(2020, 2025)])
        assert F.filter_operating_income(c) is True

    def test_two_negative_fails(self):
        ois = [100, -10, 100, -10, 100]
        c = make_company([make_year(2020 + i, operating_income=v) for i, v in enumerate(ois)])
        assert F.filter_operating_income(c) is False

    def test_one_negative_passes(self):
        ois = [100, -10, 100, 100, 100]
        c = make_company([make_year(2020 + i, operating_income=v) for i, v in enumerate(ois)])
        assert F.filter_operating_income(c) is True

    def test_empty_fails(self):
        assert F.filter_operating_income(make_company([])) is False

    def test_none_years_excluded(self):
        # None은 적자 카운트에서 제외 → 실적 있는 해는 전부 흑자라 통과
        ois = [None, 100, 100, None, 100]
        c = make_company([make_year(2020 + i, operating_income=v) for i, v in enumerate(ois)])
        assert F.filter_operating_income(c) is True


# ── 당기순이익 필터: 최근5년 합 > 0 ───────────────────────
class TestNetIncome:
    def test_positive_sum_passes(self):
        nis = [100, -50, 100, -50, 100]  # 합 200
        c = make_company([make_year(2020 + i, net_income=v) for i, v in enumerate(nis)])
        assert F.filter_net_income(c) is True

    def test_nonpositive_sum_fails(self):
        nis = [-100, -100, 50, 50, 50]  # 합 -50
        c = make_company([make_year(2020 + i, net_income=v) for i, v in enumerate(nis)])
        assert F.filter_net_income(c) is False


# ── 매출 CAGR 필터: ≥ 10% (함수 자체, apply에선 미사용) ───
class TestRevenueCagr:
    def test_growth_10pct_passes(self):
        revs = [100, 110, 121, 133.1, 146.41]  # 정확히 10%/년
        c = make_company([make_year(2020 + i, revenue=v) for i, v in enumerate(revs)])
        assert F.filter_revenue_cagr(c) is True

    def test_declining_fails(self):
        revs = [200, 180, 160, 140, 120]
        c = make_company([make_year(2020 + i, revenue=v) for i, v in enumerate(revs)])
        assert F.filter_revenue_cagr(c) is False

    def test_less_than_two_valid_passes(self):
        c = make_company([make_year(2024, revenue=100)])
        assert F.filter_revenue_cagr(c) is True


# ── 영업이익률 필터: 평균 ≥ 10% ──────────────────────────
class TestOperatingMargin:
    def test_avg_above_threshold_passes(self):
        c = make_company([make_year(2020 + i, operating_margin=0.12) for i in range(5)])
        assert F.filter_operating_margin(c) is True

    def test_avg_below_threshold_fails(self):
        c = make_company([make_year(2020 + i, operating_margin=0.05) for i in range(5)])
        assert F.filter_operating_margin(c) is False


# ── ROE 필터: 규모별 임계값 (small ≥12%) ─────────────────
class TestRoe:
    def _small_company(self, roe):
        # total_assets 1e9 (<5e9) → small bucket
        return make_company([
            make_year(2020 + i, total_assets=1_000_000_000, total_equity=1000, roe=roe)
            for i in range(5)
        ])

    def test_small_above_12pct_passes(self):
        assert F.filter_roe(self._small_company(0.13)) is True

    def test_small_below_12pct_fails(self):
        assert F.filter_roe(self._small_company(0.11)) is False

    def test_large_bucket_uses_8pct(self):
        # total_assets 2e13 (>=1e13) → large, 임계 8%
        c = make_company([
            make_year(2020 + i, total_assets=20_000_000_000_000, total_equity=1000, roe=0.09)
            for i in range(5)
        ])
        assert F.filter_roe(c) is True

    def test_capital_impaired_years_excluded(self):
        # total_equity<=0 인 해는 ROE 계산 제외, 유효 ROE 없으면 실패
        c = make_company([
            make_year(2020 + i, total_assets=1_000_000_000, total_equity=-100, roe=0.5)
            for i in range(5)
        ])
        assert F.filter_roe(c) is False


# ── apply_all_filters: revenue_cagr는 True 하드코딩(T13 문서화) ──
class TestApplyAllFilters:
    def _passing_company(self):
        years = [
            make_year(2020 + i, operating_income=100, net_income=100,
                      operating_margin=0.12, total_assets=1_000_000_000,
                      total_equity=1000, roe=0.13, revenue=100)
            for i in range(5)
        ]
        return make_company(years)

    def test_all_pass_sets_passed_all_filters(self):
        c = self._passing_company()
        F.apply_all_filters(c)
        assert c.passed_all_filters is True

    def test_revenue_cagr_always_true_even_if_declining(self):
        # 매출이 급감해도 filter_revenue_cagr는 True 고정(현 동작 캡처)
        c = self._passing_company()
        for i, y in enumerate(sorted(c.yearly_data, key=lambda d: d.year)):
            y.revenue = 1000 - i * 200  # 감소 추세
        F.apply_all_filters(c)
        assert c.filter_revenue_cagr is True

    def test_one_failing_filter_fails_overall(self):
        c = self._passing_company()
        for y in c.yearly_data:
            y.operating_margin = 0.01  # 영업이익률 미달
        F.apply_all_filters(c)
        assert c.passed_all_filters is False


# ── 2차 필터: 최근3년 평균 ROIC-WACC ≥ spread (DB 조회) ───
@pytest.mark.django_db
class TestSecondFilter:
    def _make_db_company(self, corp_code, rows):
        from apps.models import Company, YearlyFinancialData
        company = Company.objects.create(corp_code=corp_code, company_name="T")
        for year, roic, wacc in rows:
            YearlyFinancialData.objects.create(company=company, year=year, roic=roic, wacc=wacc)
        return corp_code

    def test_spread_above_threshold_passes(self):
        # 평균 roic 0.11, 평균 wacc 0.0833 → spread 0.0267 ≥ 0.02
        code = self._make_db_company("00000001", [
            (2024, 0.12, 0.08), (2023, 0.11, 0.08), (2022, 0.10, 0.09),
        ])
        assert F.check_second_filter(code) is True

    def test_spread_below_threshold_fails(self):
        # 평균 spread 0.01 < 0.02
        code = self._make_db_company("00000002", [
            (2024, 0.10, 0.09), (2023, 0.10, 0.09), (2022, 0.10, 0.09),
        ])
        assert F.check_second_filter(code) is False

    def test_no_data_fails(self):
        assert F.check_second_filter("99999999") is False
