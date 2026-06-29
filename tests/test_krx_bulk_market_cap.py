"""
전 종목 시가총액 일별 일괄 갱신(update_all_company_market_caps) 회귀 안전망.

상세 조회 시 lazy 시총 갱신을 제거한 대신, fetch_krx_daily가 호출하는 이 함수가
'하루 1회 전체 갱신'을 보장한다. 스냅샷 1회 로드 + corp->stock 역매핑 1회로 일괄 갱신.
"""
import pytest
from unittest.mock import patch, MagicMock

from apps.models import Company, YearlyFinancialData
from apps.service import krx_client


SNAP = {"rows": [
    {"ISU_CD": "111111", "MKTCAP": "500,000,000,000"},
    {"ISU_CD": "222222", "MKTCAP": "300,000,000,000"},
    {"ISU_CD": "999999", "MKTCAP": ""},      # 빈 시총 → 인덱스 제외
]}


def test_build_mktcap_index_parses_and_filters():
    idx = krx_client._build_mktcap_index(SNAP)
    assert idx == {"111111": 500000000000, "222222": 300000000000}
    assert krx_client._build_mktcap_index({"rows": []}) == {}
    assert krx_client._build_mktcap_index(None) == {}


@pytest.mark.django_db
def test_update_all_company_market_caps_wires_and_recomputes():
    c1 = Company.objects.create(corp_code="00000001", company_name="갑")
    c2 = Company.objects.create(corp_code="00000002", company_name="을")
    c3 = Company.objects.create(corp_code="00000003", company_name="병")  # 스냅샷에 종목 없음
    # c1만 연간데이터 → EV 재계산 대상
    YearlyFinancialData.objects.create(
        company=c1, year=2024, total_equity=100_000_000_000,
        interest_bearing_debt=20_000_000_000, cash_and_cash_equivalents=5_000_000_000,
    )

    fake_dart = MagicMock()
    fake_dart._corp_code_mapping_cache = {
        "111111": "00000001", "222222": "00000002", "333333": "00000003",
    }

    with patch("apps.service.krx_client.ensure_latest_snapshot", return_value=SNAP), \
         patch("apps.dart.client.DartClient", return_value=fake_dart):
        stats = krx_client.update_all_company_market_caps()

    # 시총 매칭된 c1·c2만 갱신, c3는 스냅샷에 종목 없음
    assert stats["updated"] == 2
    assert stats["skipped_not_in_snapshot"] == 1
    assert stats["skipped_no_stock"] == 0

    c1.refresh_from_db(); c2.refresh_from_db(); c3.refresh_from_db()
    assert c1.market_cap == 500000000000   # 스냅샷 입력에서 독립 산출
    assert c2.market_cap == 300000000000
    assert c3.market_cap is None

    # c1은 연간데이터가 있어 EV가 재계산되어 채워짐(시총 의존)
    yd = c1.yearly_data.get(year=2024)
    assert yd.ev is not None
    assert stats["ev_recomputed"] == 2


@pytest.mark.django_db
def test_empty_snapshot_skips():
    Company.objects.create(corp_code="00000001", company_name="갑")
    with patch("apps.service.krx_client.ensure_latest_snapshot", return_value=None):
        stats = krx_client.update_all_company_market_caps()
    assert stats == {"updated": 0, "ev_recomputed": 0,
                     "skipped_no_stock": 0, "skipped_not_in_snapshot": 0}
