"""
XBRL ACODE 기반 데이터 추출 기능 (비활성화됨)

이 파일은 XBRL 파일에서 ACODE를 이용한 추가 재무 지표 추출 기능을 포함합니다.
현재는 표본 부족으로 인해 데이터화가 어려워 기능이 중단되었습니다.

중단 이유:
- XBRL 파일에서 추출 가능한 데이터의 표본이 너무 적음
- 일부 기업만 XBRL 파일을 제공하여 일관성 있는 데이터 수집이 어려움
- 따라서 FCF, ROIC, WACC 등 계산 지표 계산도 중단됨

기능 설명:
1. XBRL 파일 다운로드 및 사업보고서 XML 추출
2. ACODE 매핑 테이블을 이용한 지표 추출
3. 추출된 지표를 YearlyFinancialDataObject에 저장

데이터 출처:
- DART Open API: download_xbrl() - XBRL 원본 파일 다운로드
- XBRL 파일 내부: 사업보고서 XML에서 ACODE 기반 지표 추출
- 매핑 테이블: xbrl_acode_mappings.json - IFRS 표준 ACODE 매핑

추출 가능한 지표:
- tangible_asset_acquisition (유형자산 취득)
- intangible_asset_acquisition (무형자산 취득)
- cfo (영업활동현금흐름)
- equity (자기자본)
- cash_and_cash_equivalents (현금및현금성자산)
- short_term_borrowings (단기차입금)
- current_portion_of_long_term_borrowings (유동성장기차입금)
- long_term_borrowings (장기차입금)
- bonds (사채)
- lease_liabilities (리스부채)
- finance_costs (금융비용)

사용 위치 (원래):
- apps/service/orchestrator.py: collect_company_data() 메서드에서 호출
- apps/service/dart.py: collect_xbrl_indicators() 메서드
- apps/service/calculator.py: calculate_all_indicators() 메서드에서 사용

관련 파일:
- apps/service/xbrl_parser.py: XBRL 파서 클래스 (현재도 코드 존재)
- apps/dart/client.py: download_xbrl(), download_xbrl_and_extract_annual_report() 메서드
- xbrl_acode_mappings.json: ACODE 매핑 테이블
"""

from apps.service.xbrl_parser import XbrlParser
from apps.models import YearlyFinancialDataObject


# ============================================================================
# apps/service/dart.py에서 주석 처리된 코드
# ============================================================================

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
    
    # 각 연도별로 처리
    for year in years:
        year_str = str(year)
        
        # 해당 연도의 YearlyFinancialData 찾기
        yearly_data = None
        for yd in company_data.yearly_data:
            if yd.year == year:
                yearly_data = yd
                break
        
        # YearlyFinancialData가 없으면 생성
        if yearly_data is None:
            yearly_data = YearlyFinancialDataObject(year=year)
            company_data.yearly_data.append(yearly_data)
       
        try:
            # 사업보고서 접수번호 조회
            try:
                rcept_no = self.client.get_annual_report_rcept_no(corp_code, year_str)
                if not rcept_no:
                    continue
            except Exception:
                continue
            
            # XBRL 다운로드 및 사업보고서 XML 추출
            xml_content = self.client.download_xbrl_and_extract_annual_report(rcept_no)
            
            # XBRL 파싱
            xbrl_data = parser.parse_xbrl_file(xml_content)
            
            # YearlyFinancialData에 채우기
            yearly_data.tangible_asset_acquisition = xbrl_data.get('tangible_asset_acquisition', 0)
            yearly_data.intangible_asset_acquisition = xbrl_data.get('intangible_asset_acquisition', 0)
            yearly_data.cfo = xbrl_data.get('cfo', 0)
            yearly_data.equity = xbrl_data.get('equity', 0)
            yearly_data.cash_and_cash_equivalents = xbrl_data.get('cash_and_cash_equivalents', 0)
            yearly_data.short_term_borrowings = xbrl_data.get('short_term_borrowings', 0)
            yearly_data.current_portion_of_long_term_borrowings = xbrl_data.get('current_portion_of_long_term_borrowings', 0)
            yearly_data.long_term_borrowings = xbrl_data.get('long_term_borrowings', 0)
            yearly_data.bonds = xbrl_data.get('bonds', 0)
            yearly_data.lease_liabilities = xbrl_data.get('lease_liabilities', 0)
            yearly_data.finance_costs = xbrl_data.get('finance_costs', 0)
            
        except Exception:
            # 예외 발생 시에도 계속 진행 (다른 연도 수집 계속)
            pass


# ============================================================================
# apps/service/orchestrator.py에서 주석 처리된 코드
# ============================================================================

def collect_xbrl_data_in_orchestrator_disabled(self, corp_code: str, years: list[int]):
    """
    오케스트레이터에서 XBRL 데이터 수집 (비활성화됨)
    
    원래 위치: apps/service/orchestrator.py의 DataOrchestrator.collect_company_data() 메서드 내부
    
    Args:
        corp_code: 고유번호 (8자리)
        years: 수집할 연도 리스트
    
    원래 코드:
        # XBRL 데이터 수집 (가장 최근 년도만 수집)
        # 표본이 너무 적어서 데이터화를 못할듯하여 일단 중단
        # try:
        #     latest_year = [max(years)] if years else []
        #     if latest_year:
        #         self.dart_service.collect_xbrl_indicators(corp_code, latest_year, company_data)
        # except Exception as e:
        #     # XBRL 수집 실패 시에도 기본 지표 수집은 계속 진행
        #     pass
    """
    # XBRL 데이터 수집 (가장 최근 년도만 수집)
    # 표본이 너무 적어서 데이터화를 못할듯하여 일단 중단
    try:
        latest_year = [max(years)] if years else []
        if latest_year:
            self.dart_service.collect_xbrl_indicators(corp_code, latest_year, company_data)
    except Exception:
        # XBRL 수집 실패 시에도 기본 지표 수집은 계속 진행
        pass


# ============================================================================
# apps/service/calculator.py에서 주석 처리된 코드
# ============================================================================

def calculate_all_indicators_disabled(cls, company_data, tax_rate=0.25, equity_risk_premium=5.0):
    """
    모든 계산 지표 채우기 (비활성화됨)
    
    원래 위치: apps/service/calculator.py의 IndicatorCalculator 클래스 메서드
    
    주의: XBRL 데이터 수집이 중단되어 계산 지표 계산도 중단되었습니다.
    FCF, ICR, ROIC, WACC 계산에 필요한 데이터(CFO, 금융비용, 자기자본 등)는
    XBRL에서만 수집 가능하며, 표본이 너무 적어서 데이터화를 못할듯하여 일단 중단했습니다.
    
    Args:
        company_data: CompanyFinancialObject 객체
        tax_rate: 법인세율 (기본값: 0.25)
        equity_risk_premium: 주주기대수익률 (기본값: 5.0)
    
    원래 코드:
        # XBRL 데이터 수집 중단으로 인해 계산 지표 계산도 중단
        # 가장 최근 년도만 계산 (XBRL 데이터 수집의 한계)
        # latest_data = max(company_data.yearly_data, key=lambda x: x.year)
        # 
        # # FCF 계산
        # latest_data.fcf = cls.calculate_fcf(latest_data)
        # 
        # # ICR 계산 주석 처리
        # # 해당 계산에 이자비용을 금융비용으로 대체했으나 계산값이 너무 튀어 일단 주석처리함
        # # latest_data.icr = cls.calculate_icr(latest_data)
        # 
        # # ROIC 계산
        # latest_data.roic = cls.calculate_roic(latest_data, tax_rate)
        # 
        # # WACC 계산 주석 처리
        # # 해당 계산에 이자비용을 금융비용으로 대체했으나 계산값이 너무 튀어 일단 주석처리함
        # # latest_data.wacc = cls.calculate_wacc(
        # #     latest_data,
        # #     company_data.bond_yield_5y,
        # #     tax_rate,
        # #     equity_risk_premium
        # # )
    """
    if not company_data.yearly_data:
        return
    
    # XBRL 데이터 수집 중단으로 인해 계산 지표 계산도 중단
    # 가장 최근 년도만 계산 (XBRL 데이터 수집의 한계)
    latest_data = max(company_data.yearly_data, key=lambda x: x.year)
    
    # FCF 계산
    # latest_data.fcf = cls.calculate_fcf(latest_data)
    
    # ICR 계산 주석 처리
    # 해당 계산에 이자비용을 금융비용으로 대체했으나 계산값이 너무 튀어 일단 주석처리함
    # latest_data.icr = cls.calculate_icr(latest_data)
    
    # ROIC 계산
    # latest_data.roic = cls.calculate_roic(latest_data, tax_rate)
    
    # WACC 계산 주석 처리
    # 해당 계산에 이자비용을 금융비용으로 대체했으나 계산값이 너무 튀어 일단 주석처리함
    # latest_data.wacc = cls.calculate_wacc(
    #     latest_data,
    #     company_data.bond_yield_5y,
    #     tax_rate,
    #     equity_risk_premium
    # )
