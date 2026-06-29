"""
고급지표(ROIC/WACC/FCF) 수집의 CFS→OFS 폴백 회귀 안전망.

버그: _fill_advanced_indicators가 전체재무제표를 CFS(연결)만 조회하고 OFS(별도)
폴백이 없어, 연결재무제표를 내지 않는 중소형사(별도만 제출)는 cash·이자부채·CFO를
못 잡아 ROIC/WACC/FCF가 전부 None이 됐다(예: 삼미금속 - 실데이터로 확인).

이 테스트는 'CFS가 빈 리스트면 OFS로 폴백해 추출이 성공한다'를 박제한다.
구현 전에는 RED(roic/wacc None, cash 0)여야 한다.
"""
from unittest.mock import MagicMock

from apps.service.orchestrator import DataOrchestrator
from apps.models import CompanyFinancialObject, YearlyFinancialDataObject


def _row(sj, aid, nm, th):
    return {"sj_div": sj, "account_id": aid, "account_nm": nm,
            "thstrm_amount": th, "frmtrm_amount": None, "bfefrmtrm_amount": None}


# 별도(OFS)재무제표 합성 행: cash/이자부채/CFO/CAPEX/이자비용이 모두 잡히도록 구성
OFS_ROWS = [
    _row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "1000000000"),
    _row("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "유형자산의 취득", "100000000"),
    _row("CF", "dart_CashAndCashEquivalentsAtEndOfPeriodCf", "기말현금및현금성자산", "500000000"),
    _row("CF", "ifrs-full_InterestPaidClassifiedAsOperatingActivities", "이자의 지급", "20000000"),
    _row("BS", "ifrs-full_ShorttermBorrowings", "단기차입금", "300000000"),
]


def _make_company():
    company_data = CompanyFinancialObject()
    company_data.corp_code = "00125664"  # 삼미금속 (OFS-only 실사례)
    company_data.company_name = "삼미금속(주)"
    company_data.latest_annual_report_year = 2023
    yd = YearlyFinancialDataObject(year=2023)
    yd.operating_income = 200000000
    yd.total_equity = 1000000000
    company_data.yearly_data = [yd]
    return company_data, yd


def test_cfs_empty_falls_back_to_ofs():
    """CFS가 빈 리스트면 OFS로 폴백해 cash/이자부채/ROIC/WACC가 채워진다."""
    orch = DataOrchestrator()

    def fake_all(corp_code, bsns_year, reprt_code="11011", fs_div="CFS"):
        return [] if fs_div == "CFS" else OFS_ROWS

    orch.dart_client = MagicMock()
    orch.dart_client.get_financial_statement_all.side_effect = fake_all

    company_data, yd = _make_company()
    orch._fill_advanced_indicators(company_data, bond_yield_decimal=0.03)

    # OFS 폴백이 동작했다면 추출값이 박혀야 한다
    assert yd.cash_and_cash_equivalents == 500000000, "OFS 현금 미추출"
    assert yd.interest_bearing_debt == 300000000, "OFS 이자부채 미추출"
    assert yd.roic is not None, "ROIC가 None (OFS 폴백 실패)"
    assert yd.wacc is not None, "WACC가 None (OFS 폴백 실패)"
    assert yd.fcf is not None, "FCF가 None (OFS 폴백 실패)"


def test_cfs_present_does_not_call_ofs():
    """CFS가 데이터를 주면 OFS는 조회하지 않는다(기존 동작 보존)."""
    orch = DataOrchestrator()
    cfs_rows = OFS_ROWS  # CFS로 동일 계정이 온다고 가정

    calls = []

    def fake_all(corp_code, bsns_year, reprt_code="11011", fs_div="CFS"):
        calls.append(fs_div)
        return cfs_rows if fs_div == "CFS" else []

    orch.dart_client = MagicMock()
    orch.dart_client.get_financial_statement_all.side_effect = fake_all

    company_data, yd = _make_company()
    orch._fill_advanced_indicators(company_data, bond_yield_decimal=0.03)

    assert "OFS" not in calls, "CFS가 있는데 OFS를 불필요하게 조회함"
    assert yd.cash_and_cash_equivalents == 500000000
