"""
수집 시점 시가총액·EV/IC eager 채움 회귀 안전망.

기존엔 시총을 기업 상세 조회 시 lazy 호출(fetch_and_save_company_market_cap)했으나,
수집 단계에서 바로 채우도록 이동. 핵심 제약:
- KRX 스냅샷은 시장별 대용량 JSON이라 회사마다 재병합하면 안 됨 → 배치당 1회 인덱싱.
- 스냅샷에 종목이 없으면 조용히 생략(시총 실패가 회사 수집 실패가 되면 안 됨).
"""
from unittest.mock import patch

from apps.service.orchestrator import DataOrchestrator


SNAP = {"rows": [
    {"ISU_CD": "005930", "MKTCAP": "400,000,000,000"},
    {"ISU_CD": "000660", "MKTCAP": "100,000,000,000"},
    {"ISU_CD": "BADXX", "MKTCAP": ""},      # 빈 시총 → 제외
    {"ISU_CD": "", "MKTCAP": "5,000"},      # 종목코드 없음 → 제외
]}


def test_ensure_krx_index_builds_and_caches():
    """스냅샷 rows를 {종목코드: 시총(int)} 인덱스로 만들고, 1회만 로드(캐시)한다."""
    orch = DataOrchestrator()
    with patch("apps.service.krx_client.ensure_latest_snapshot", return_value=SNAP) as m:
        idx = orch._ensure_krx_index()
        assert idx == {"005930": 400000000000, "000660": 100000000000}
        idx2 = orch._ensure_krx_index()
        assert m.call_count == 1, "스냅샷을 회사마다 재로드하면 안 됨(캐시)"
        assert idx2 is idx


def test_fill_market_cap_and_ev_uses_lookup():
    """종목코드로 시총을 조회해 그 값으로 EV/IC 재계산을 호출한다."""
    orch = DataOrchestrator()
    orch._krx_index = {"005930": 400000000000}
    with patch("apps.service.corp_code.get_stock_code_by_corp_code", return_value="005930"), \
         patch("apps.service.db.run_with_write_lock_retry"), \
         patch("apps.service.db.recompute_and_save_ev_ic") as mrec:
        orch._fill_market_cap_and_ev("00126380")
        mrec.assert_called_once_with("00126380", 400000000000)


def test_fill_market_cap_skips_when_not_in_snapshot():
    """스냅샷에 종목이 없으면 EV 재계산을 호출하지 않는다(조용히 생략)."""
    orch = DataOrchestrator()
    orch._krx_index = {"005930": 400000000000}
    with patch("apps.service.corp_code.get_stock_code_by_corp_code", return_value="999999"), \
         patch("apps.service.db.recompute_and_save_ev_ic") as mrec:
        orch._fill_market_cap_and_ev("00000000")
        mrec.assert_not_called()
