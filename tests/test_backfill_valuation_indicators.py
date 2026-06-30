"""
RED 박제: management command `backfill_valuation_indicators` (신설 예정, 아직 없음).

추론한 인터페이스: apps/management/commands/backfill_valuation_indicators.py.
DB의 전 회사 YearlyFinancialData를 순회, 저장된 입력으로 5선 지표 계산 후 재저장.
call_command('backfill_valuation_indicators') 로 호출.

기대값은 손계산 독립값(calculate_* 실행출력 복사 금지) — test_fill_valuation_indicators.py와 동일 입력.
"""
import pytest
from django.core.management import call_command

from apps.models import Company, YearlyFinancialData


@pytest.mark.django_db
class TestBackfillCommand:
    def _make_row(self, corp_code="00000001", year=2024, roic=0.20):
        c = Company.objects.create(corp_code=corp_code, company_name="테스트기업")
        # 입력 필드 채움, 5선 컬럼은 None(미계산)
        YearlyFinancialData.objects.create(
            company=c, year=year,
            roic=roic, net_income=1000, dividend_paid=400,
            total_assets=10000, total_liabilities=4000, total_equity=6000,
            current_assets=5000, current_liabilities=2000,
            retained_earnings=3000, operating_income=1500,
            sustainable_growth=None, altman_z=None, altman_z_class=None,
            zmijewski=None, zmijewski_flag=None,
        )
        return c

    def test_backfills_five_columns(self):
        self._make_row()
        call_command("backfill_valuation_indicators")
        yd = YearlyFinancialData.objects.get(company_id="00000001", year=2024)
        # 손계산 (test_fill_valuation_indicators.py 케이스 a와 동일)
        assert yd.sustainable_growth == pytest.approx(0.12)        # 0.20*0.6
        assert yd.altman_z == pytest.approx(8.779)                 # 3.25+1.968+0.978+1.008+1.575
        assert yd.altman_z_class == "safe"                         # 8.779>=2.6
        assert yd.zmijewski == pytest.approx(0.075460, abs=1e-4)   # 1/(1+e^2.5057)
        assert yd.zmijewski_flag is False                          # 0.0754596<0.5

    def test_roic_none_row_growth_stays_none_but_processed(self):
        # roic=None 연도 행: g는 None으로 남되, 나머지는 계산돼 command가 처리했음을 증명
        self._make_row(corp_code="00000002", year=2023, roic=None)
        call_command("backfill_valuation_indicators")
        yd = YearlyFinancialData.objects.get(company_id="00000002", year=2023)
        assert yd.sustainable_growth is None       # calculate_g: roic None → None
        assert yd.altman_z == pytest.approx(8.779)  # 처리됐다는 증거(동어반복 방지)
        assert yd.altman_z_class == "safe"
