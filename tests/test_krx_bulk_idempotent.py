"""
[작업6] 일별 배치 멱등(무변동 skip) RED 박제.

박제할 동작(update_all_company_market_caps):
 - 같은 스냅샷·같은 시총으로 두 번 실행하면 두 번째는 무변동이라 updated==0,
   그리고 recompute_and_save_ev_ic가 한 번도 안 불림(무변동 EV 재계산 skip).
현재: 기존 시총과 비교 없이 매번 update·recompute → 두 번째도 updated==2.

기대값 출처: 사용자 명세(첫 실행 updated==2, 둘째 실행 updated==0·recompute 0회).
패치 방식은 기존 test_krx_bulk_market_cap.py의 wires_and_recomputes 테스트와 동일.
구현 전 RED 사유: 기존 market_cap과 비교해 무변동을 skip하는 로직 부재.
"""
from unittest.mock import patch, MagicMock

import pytest

from apps.models import Company
from apps.service import krx_client


SNAP = {"rows": [
    {"ISU_CD": "111111", "MKTCAP": "500,000,000,000"},
    {"ISU_CD": "222222", "MKTCAP": "300,000,000,000"},
]}


@pytest.mark.django_db
def test_second_run_is_idempotent_skips_unchanged():
    Company.objects.create(corp_code="00000001", company_name="갑")   # 초기 market_cap=None
    Company.objects.create(corp_code="00000002", company_name="을")
    fake_dart = MagicMock()
    fake_dart._corp_code_mapping_cache = {"111111": "00000001", "222222": "00000002"}

    with patch("apps.service.krx_client.ensure_latest_snapshot", return_value=SNAP), \
         patch("apps.dart.client.DartClient", return_value=fake_dart), \
         patch("apps.service.db.recompute_and_save_ev_ic") as spy:
        stats1 = krx_client.update_all_company_market_caps()
        assert stats1["updated"] == 2           # 첫 실행: None→값, 2건 갱신

        spy.reset_mock()
        stats2 = krx_client.update_all_company_market_caps()
        assert stats2["updated"] == 0           # 둘째: 같은 시총 → 무변동 skip
        assert spy.call_count == 0              # 무변동이면 EV 재계산 호출 안 함
