"""
[작업4] bas_dd → KST aware datetime 헬퍼 + 갱신 타임스탬프 반영 RED 박제.

박제할 동작:
 - apps.service.krx_client._bas_dd_to_aware_datetime("YYYYMMDD") -> 그날 0시 KST aware datetime.
   잘못된 입력(빈/None/길이≠8/잘못된 날짜)은 None.
 - update_all_company_market_caps가 market_cap_updated_at을 스냅샷 bas_dd(그날 0시)로 반영(now 아님).

기대값 출처: 사용자 명세 표(연/월/일/시=2026/6/26/0, None 케이스) 및 "bas_dd 그날 0시 KST".
추론 인터페이스: krx_client._bas_dd_to_aware_datetime(str|None)->datetime|None.
구현 전 RED 사유:
 - _bas_dd_to_aware_datetime 미존재(AttributeError).
 - update_all_company_market_caps가 timezone.now()를 써서 날짜가 bas_dd(2026-06-26)가 아님.
"""
from datetime import date, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest

from apps.models import Company
from apps.service import krx_client

KST = timezone(timedelta(hours=9))


def test_bas_dd_valid_returns_kst_midnight_aware():
    dt = krx_client._bas_dd_to_aware_datetime("20260626")
    assert dt is not None
    assert dt.tzinfo is not None                  # aware
    assert dt.utcoffset() == timedelta(hours=9)   # KST(+09:00)
    assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 6, 26, 0)  # 그날 0시


@pytest.mark.parametrize("bad", ["", None, "2026", "20261332"])
def test_bas_dd_invalid_returns_none(bad):
    # "":빈값, None, "2026":길이≠8, "20261332":잘못된 날짜 → 모두 None(명세)
    assert krx_client._bas_dd_to_aware_datetime(bad) is None


@pytest.mark.django_db
def test_update_uses_bas_dd_for_market_cap_updated_at():
    c = Company.objects.create(corp_code="00000001", company_name="갑")
    snap = {"bas_dd": "20260626",
            "rows": [{"ISU_CD": "111111", "MKTCAP": "500,000,000,000"}]}
    fake_dart = MagicMock()
    fake_dart._corp_code_mapping_cache = {"111111": "00000001"}
    with patch("apps.service.krx_client.ensure_latest_snapshot", return_value=snap), \
         patch("apps.dart.client.DartClient", return_value=fake_dart):
        krx_client.update_all_company_market_caps()
    c.refresh_from_db()
    assert c.market_cap == 500000000000            # 전제: 시총 갱신됨
    assert c.market_cap_updated_at is not None
    # now가 아니라 스냅샷 bas_dd → KST로 변환한 날짜가 2026-06-26
    assert c.market_cap_updated_at.astimezone(KST).date() == date(2026, 6, 26)
