"""
RED 박제 (방향 B / 대상 2·3): 미계산(roic==0.0) 행의 roic/wacc/fcf를 None으로 정리.

추론한 인터페이스: apps.service.db.nullify_uncomputed_indicators() — 모듈 함수(신설 예정, 아직 없음).
  동작: DB의 YearlyFinancialData 중 roic==0.0(미계산)인 모든 행의 roic·wacc·fcf를 None으로 갱신,
        계산된 행(roic!=0)은 미변경. 정리한 행 수를 반환.
  데이터 마이그레이션이 RunPython으로 이 함수를 호출할 예정이나, 테스트는 함수를 직접 호출해 검증.

대상 3 통합: nullify -> backfill 순으로 실행하면 미계산 행의 sustainable_growth는 None으로 남고
            (roic이 None이 됐으므로), 입력이 있는 altman_z는 계산됨(비-None) — "g만 죽이고 Z''는 살림".
  backfill 인터페이스: call_command('backfill_valuation_indicators') (test_backfill_valuation_indicators.py 와 동일).
"""
import pytest
from django.core.management import call_command

from apps.models import Company, YearlyFinancialData
from apps.service.db import nullify_uncomputed_indicators


@pytest.mark.django_db
class TestNullifyUncomputedIndicators:
    """대상 2: 미계산 행은 None, 계산 행은 보존, 반환=정리 행수."""

    def _setup_rows(self):
        c = Company.objects.create(corp_code="00000001", company_name="테스트기업")
        # fixture A (미계산): roic=0.0 -> 정리 대상
        YearlyFinancialData.objects.create(
            company=c, year=2024,
            roic=0.0, wacc=0.0, fcf=0, net_income=1000,
        )
        # fixture B (계산됨): roic=0.15 -> 절대 미변경
        YearlyFinancialData.objects.create(
            company=c, year=2023,
            roic=0.15, wacc=0.08, fcf=100,
        )
        return c

    def test_uncomputed_row_nulled(self):
        # 출처: 대상 2 — A행 roic/wacc/fcf 전부 None
        self._setup_rows()
        nullify_uncomputed_indicators()
        a = YearlyFinancialData.objects.get(company_id="00000001", year=2024)
        assert a.roic is None
        assert a.wacc is None
        assert a.fcf is None

    def test_computed_row_preserved(self):
        # 출처: 대상 2 반동어반복 가드 — B행은 보존(전부 None으로 만드는 잘못된 구현을 잡음)
        self._setup_rows()
        nullify_uncomputed_indicators()
        b = YearlyFinancialData.objects.get(company_id="00000001", year=2023)
        assert b.roic == pytest.approx(0.15)
        assert b.wacc == pytest.approx(0.08)
        assert b.fcf == 100

    def test_returns_nullified_row_count(self):
        # 출처: 대상 2 — 정리한 행 수 반환(미계산 A 1행만)
        self._setup_rows()
        assert nullify_uncomputed_indicators() == 1


@pytest.mark.django_db
class TestNullifyThenBackfill:
    """대상 3: 정리->백필 연계 — g는 None으로 남고 Z''는 입력으로 계산됨."""

    def _make_uncomputed_row_with_z_inputs(self):
        c = Company.objects.create(corp_code="00000002", company_name="통합기업")
        # roic=0.0(미계산). Z'' 계산 가능하도록 입력 채움.
        # 입력 출처/Z'' 손계산: test_fill_valuation_indicators.py 케이스 (a)와 동일 입력.
        YearlyFinancialData.objects.create(
            company=c, year=2024,
            roic=0.0, wacc=0.0, fcf=0,
            net_income=1000, dividend_paid=400,
            total_assets=10000, total_liabilities=4000, total_equity=6000,
            current_assets=5000, current_liabilities=2000,
            retained_earnings=3000, operating_income=1500,
        )
        return c

    def test_g_dies_but_z_survives(self):
        self._make_uncomputed_row_with_z_inputs()
        nullify_uncomputed_indicators()
        call_command("backfill_valuation_indicators")
        yd = YearlyFinancialData.objects.get(company_id="00000002", year=2024)
        # 정리로 roic이 None이 됐음(메커니즘 확인)
        assert yd.roic is None
        # g: calculate_g 가 roic None -> None
        assert yd.sustainable_growth is None
        # Z''는 입력으로 계산됨(비-None). 독립 손계산(docstring 4변수 공식):
        #   Z'' = 3.25 + 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4
        #   X1=(5000-2000)/10000=0.3, X2=3000/10000=0.3,
        #   X3=1500/10000=0.15, X4=6000/4000=1.5
        #   = 3.25+1.968+0.978+1.008+1.575 = 8.779
        assert yd.altman_z == pytest.approx(8.779)
        assert yd.altman_z_class == "safe"  # 8.779 >= 2.6
