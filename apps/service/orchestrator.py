"""
데이터 수집 오케스트레이터
"""
from apps.service.dart import DartDataService
from apps.service.ecos import EcosDataService
from apps.service.calculator import IndicatorCalculator
from apps.models import CompanyFinancialObject, YearlyFinancialData
from apps.dart.client import DartClient


class DataOrchestrator:
    """DART와 ECOS 데이터 수집을 조율하는 오케스트레이터"""
    
    def __init__(self):
        self.dart_service = DartDataService()
        self.ecos_service = EcosDataService()
        self.dart_client = DartClient()
    
    def collect_company_data(self, corp_code: str) -> CompanyFinancialObject:
        """
        회사 데이터 수집 (DART + ECOS)
        
        Args:
            corp_code: 고유번호 (8자리)
        
        Returns:
            CompanyFinancialObject
        """
        # CompanyFinancialObject 생성
        company_data = CompanyFinancialObject()
        company_data.corp_code = corp_code
        
        # 기업 기본 정보 조회
        try:
            company_info = self.dart_client.get_company_info(corp_code)
            if company_info:
                company_data.company_name = company_info.get('corp_name', '')
                company_data.business_type_code = company_info.get('induty_code', '')
                company_data.business_type_name = company_info.get('corp_cls', '')
        except Exception as e:
            print(f"경고: 기업 정보 조회 실패: {e}")
        
        # 최근 5년 연도 리스트 생성
        years = self.dart_service._get_recent_years(5)
        
        # DART 기본 지표 수집 (한 번의 호출로 모든 연도 처리)
        self.dart_service.fill_basic_indicators(corp_code, years, company_data)
        
        # XBRL 데이터 수집
        try:
            self.dart_service.collect_xbrl_indicators(corp_code, years, company_data)
        except Exception as e:
            # XBRL 수집 실패 시에도 기본 지표 수집은 계속 진행
            pass
        
        # ECOS 데이터 수집 (채권수익률 - 가장 최근 값 한 번만 수집)
        try:
            bond_yield = self.ecos_service.collect_bond_yield_5y()
            company_data.bond_yield_5y = bond_yield
        except Exception as e:
            print(f"경고: 채권수익률 수집 실패: {e}")
            # 채권수익률은 실패해도 계속 진행
        
        # 계산 로직 호출하여 계산 지표 채우기
        try:
            IndicatorCalculator.calculate_all_indicators(company_data)
        except Exception as e:
            print(f"경고: 계산 지표 계산 실패: {e}")
            # 계산 실패 시에도 수집된 데이터는 반환
        
        # (추후) DB 저장 로직
        # self._save_to_db(company_data)
        
        return company_data


