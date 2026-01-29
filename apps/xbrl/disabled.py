"""
XBRL ACODE 기반 데이터 추출 기능 (비활성화됨)

이 파일은 XBRL 파일에서 ACODE를 이용한 추가 재무 지표 추출 기능을 포함합니다.
현재는 표본 부족으로 인해 데이터화가 어려워 기능이 중단되었습니다.

중단 이유:
- XBRL 파일에서 추출 가능한 데이터의 표본이 너무 적음
- 일부 기업만 XBRL 파일을 제공하여 일관성 있는 데이터 수집이 어려움
- 따라서 FCF, ROIC, WACC 등 계산 지표 계산도 중단됨

기능 설명:
1. XBRL 파일 다운로드 및 사업보고서 XML 추출 (apps.xbrl.download, extract)
2. ACODE 매핑 테이블을 이용한 지표 추출
3. 추출된 지표를 YearlyFinancialDataObject에 저장

데이터 출처:
- apps.xbrl.download: download_xbrl() - DART document.xml 호출
- apps.xbrl.extract: extract_annual_report_from_xbrl()
- XBRL 파일 내부: 사업보고서 XML에서 ACODE 기반 지표 추출
- 매핑 테이블: xbrl_acode_mappings.json
"""

from apps.xbrl.parser import XbrlParser
from apps.xbrl.extract import extract_annual_report_from_xbrl
from apps.models import YearlyFinancialDataObject


def collect_xbrl_indicators_disabled(self, corp_code: str, years: list[int], company_data):
    """
    XBRL 파일에서 추가 지표 수집 (비활성화됨)

    원래 위치: apps/service/dart.py의 DartDataService 클래스 메서드

    Args:
        corp_code: 고유번호 (8자리)
        years: 수집할 연도 리스트
        company_data: 채울 CompanyFinancialObject 객체 (in-place 수정)
    """
    parser = XbrlParser()

    for year in years:
        year_str = str(year)

        yearly_data = None
        for yd in company_data.yearly_data:
            if yd.year == year:
                yearly_data = yd
                break

        if yearly_data is None:
            yearly_data = YearlyFinancialDataObject(year=year)
            company_data.yearly_data.append(yearly_data)

        try:
            try:
                rcept_no = self.client.get_annual_report_rcept_no(corp_code, year_str)
                if not rcept_no:
                    continue
            except Exception:
                continue

            xml_content = extract_annual_report_from_xbrl(rcept_no)

            xbrl_data = parser.parse_xbrl_file(xml_content)

            yearly_data.tangible_asset_acquisition = xbrl_data.get("tangible_asset_acquisition", 0)
            yearly_data.intangible_asset_acquisition = xbrl_data.get("intangible_asset_acquisition", 0)
            yearly_data.cfo = xbrl_data.get("cfo", 0)
            yearly_data.equity = xbrl_data.get("equity", 0)
            yearly_data.cash_and_cash_equivalents = xbrl_data.get("cash_and_cash_equivalents", 0)
            yearly_data.short_term_borrowings = xbrl_data.get("short_term_borrowings", 0)
            yearly_data.current_portion_of_long_term_borrowings = xbrl_data.get(
                "current_portion_of_long_term_borrowings", 0
            )
            yearly_data.long_term_borrowings = xbrl_data.get("long_term_borrowings", 0)
            yearly_data.bonds = xbrl_data.get("bonds", 0)
            yearly_data.lease_liabilities = xbrl_data.get("lease_liabilities", 0)
            yearly_data.finance_costs = xbrl_data.get("finance_costs", 0)

        except Exception:
            pass


def collect_xbrl_data_in_orchestrator_disabled(self, corp_code: str, years: list[int]):
    """오케스트레이터에서 XBRL 데이터 수집 (비활성화됨)"""
    try:
        latest_year = [max(years)] if years else []
        if latest_year:
            self.dart_service.collect_xbrl_indicators(corp_code, latest_year, company_data)
    except Exception:
        pass


def calculate_all_indicators_disabled(cls, company_data, tax_rate=0.25, equity_risk_premium=5.0):
    """모든 계산 지표 채우기 (비활성화됨)"""
    if not company_data.yearly_data:
        return
    latest_data = max(company_data.yearly_data, key=lambda x: x.year)
