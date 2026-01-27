"""
데이터 수집 오케스트레이터
"""
from apps.service.dart import DartDataService
from apps.service.ecos import EcosDataService
from apps.service.calculator import IndicatorCalculator
from apps.service.filter import CompanyFilter
from apps.models import CompanyFinancialObject, YearlyFinancialDataObject
from apps.dart.client import DartClient
from apps.utils.utils import is_financial_industry, save_company_to_db


class DataOrchestrator:
    """DART와 ECOS 데이터 수집을 조율하는 오케스트레이터"""
    
    def __init__(self):
        self.dart_service = DartDataService()
        self.ecos_service = EcosDataService()
        self.dart_client = DartClient()
    
    def collect_company_data(self, corp_code: str, save_to_db: bool = True) -> CompanyFinancialObject:
        """
        회사 데이터 수집 (DART + ECOS)
        
        Args:
            corp_code: 고유번호 (8자리)
            save_to_db: DB 저장 여부 (기본값: True, 병렬 처리 시 False로 설정)
        
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
                induty_code = company_info.get('induty_code', '')
                company_data.business_type_code = induty_code
                
                # 금융업 여부 판별
                is_financial = is_financial_industry(induty_code)
                company_data.business_type_name = "금융업" if is_financial else "비금융업"
        except Exception as e:
            print(f"경고: 기업 정보 조회 실패: {e}")
        
        # 최근 5년 연도 리스트 생성
        years = self.dart_service._get_recent_years(5)
        
        # DART 기본 지표 수집 (한 번의 호출로 모든 연도 처리)
        self.dart_service.fill_basic_indicators(corp_code, years, company_data)
        
        # 기본 재무지표 계산 (영업이익률, ROE)
        # API 호출 최적화를 위해 재무지표 API 호출을 제거하고 계산 방식으로 변경
        IndicatorCalculator.calculate_basic_financial_ratios(company_data)
        
        # XBRL 데이터 수집 (가장 최근 년도만 수집)
        # 표본이 너무 적어서 데이터화를 못할듯하여 일단 중단
        # try:
        #     latest_year = [max(years)] if years else []
        #     if latest_year:
        #         self.dart_service.collect_xbrl_indicators(corp_code, latest_year, company_data)
        # except Exception as e:
        #     # XBRL 수집 실패 시에도 기본 지표 수집은 계속 진행
        #     pass
        
        # ECOS 데이터 수집 (채권수익률 - 하루 기준으로 캐싱)
        try:
            from django.utils import timezone
            from datetime import timedelta
            from django.apps import apps as django_apps
            
            BondYieldModel = django_apps.get_model('apps', 'BondYield')
            
            # DB에서 채권수익률 조회 (단일 레코드만 유지)
            bond_yield_obj, created = BondYieldModel.objects.get_or_create(
                id=1,  # 단일 레코드
                defaults={
                    'yield_value': 0.0,
                    'collected_at': timezone.now() - timedelta(days=2)  # 기본값: 2일 전
                }
            )
            
            # 하루가 지났는지 확인
            if timezone.now() - bond_yield_obj.collected_at > timedelta(days=1):
                # ECOS API 호출하여 업데이트
                bond_yield = self.ecos_service.collect_bond_yield_5y()
                # ECOS API는 백분율로 반환하므로 소수로 변환 (예: 3.057% -> 0.03057)
                bond_yield_value = bond_yield / 100.0 if bond_yield else 0.0
                bond_yield_obj.yield_value = bond_yield_value
                bond_yield_obj.collected_at = timezone.now()
                bond_yield_obj.save()
            else:
                # 캐시된 값 사용
                bond_yield_value = bond_yield_obj.yield_value
            
            company_data.bond_yield_5y = bond_yield_value
        except Exception as e:
            print(f"경고: 채권수익률 수집 실패: {e}")
            # 채권수익률은 실패해도 계속 진행
            company_data.bond_yield_5y = 0.0
        
        # 계산 로직 호출하여 계산 지표 채우기
        # try:
        #     IndicatorCalculator.calculate_all_indicators(company_data)
        # except Exception as e:
        #     print(f"경고: 계산 지표 계산 실패: {e}")
        #     # 계산 실패 시에도 수집된 데이터는 반환
        
        # 필터 적용
        try:
            CompanyFilter.apply_all_filters(company_data)
        except Exception as e:
            print(f"경고: 필터 적용 실패: {e}")
            # 필터 실패 시에도 수집된 데이터는 반환
        
        # DB 저장 로직 (save_to_db가 True일 때만 실행)
        if save_to_db:
            try:
                save_company_to_db(company_data)
            except Exception as e:
                print(f"경고: DB 저장 실패: {e}")
                # DB 저장 실패 시에도 수집된 데이터는 반환
        
        return company_data


