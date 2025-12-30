"""
데이터 수집 오케스트레이터
"""
from apps.service.dart import DartDataService
from apps.service.ecos import EcosDataService
from apps.service.calculator import IndicatorCalculator
from apps.service.filter import CompanyFilter
from apps.models import CompanyFinancialObject, YearlyFinancialDataObject
from apps.dart.client import DartClient
from apps.utils.utils import is_financial_industry


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
        
        # DART 재무지표 수집 (매출총이익률, 판관비율, 총자산영업이익률, ROE)
        try:
            self.dart_service.fill_financial_indicators(corp_code, years, company_data)
        except Exception as e:
            # 재무지표 수집 실패 시에도 기본 지표 수집은 계속 진행
            print(f"경고: 재무지표 수집 실패: {e}")
            import traceback
            traceback.print_exc()
        
        # XBRL 데이터 수집 (가장 최근 년도만 수집)
        # 표본이 너무 적어서 데이터화를 못할듯하여 일단 중단
        # try:
        #     latest_year = [max(years)] if years else []
        #     if latest_year:
        #         self.dart_service.collect_xbrl_indicators(corp_code, latest_year, company_data)
        # except Exception as e:
        #     # XBRL 수집 실패 시에도 기본 지표 수집은 계속 진행
        #     pass
        
        # ECOS 데이터 수집 (채권수익률 - 가장 최근 값 한 번만 수집)
        try:
            bond_yield = self.ecos_service.collect_bond_yield_5y()
            # ECOS API는 백분율로 반환하므로 소수로 변환 (예: 3.057% -> 0.03057)
            company_data.bond_yield_5y = bond_yield / 100.0 if bond_yield else 0.0
        except Exception as e:
            print(f"경고: 채권수익률 수집 실패: {e}")
            # 채권수익률은 실패해도 계속 진행
        
        # 계산 로직 호출하여 계산 지표 채우기
        try:
            IndicatorCalculator.calculate_all_indicators(company_data)
        except Exception as e:
            print(f"경고: 계산 지표 계산 실패: {e}")
            # 계산 실패 시에도 수집된 데이터는 반환
        
        # 필터 적용
        try:
            CompanyFilter.apply_all_filters(company_data)
        except Exception as e:
            print(f"경고: 필터 적용 실패: {e}")
            # 필터 실패 시에도 수집된 데이터는 반환
        
        # DB 저장 로직
        try:
            self._save_to_db(company_data)
        except Exception as e:
            print(f"경고: DB 저장 실패: {e}")
            # DB 저장 실패 시에도 수집된 데이터는 반환
        
        return company_data
    
    def _save_to_db(self, company_data: CompanyFinancialObject) -> None:
        """
        CompanyFinancialObject를 Django 모델로 변환하여 DB에 저장
        
        Args:
            company_data: CompanyFinancialObject 객체
        """
        # Django 모델 import (Python 클래스와 이름 충돌 방지)
        # Django 모델은 models.Model을 상속받으므로 isinstance로 확인 가능
        # 하지만 더 안전하게 모듈에서 직접 접근
        import django.apps
        from django.apps import apps as django_apps
        
        # Django 모델 가져오기
        CompanyModel = django_apps.get_model('apps', 'Company')
        YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
        
        # Company 모델 저장 또는 업데이트
        company, created = CompanyModel.objects.get_or_create(
            corp_code=company_data.corp_code,
            defaults={
                'company_name': company_data.company_name,
                'business_type_code': company_data.business_type_code,
                'business_type_name': company_data.business_type_name,
                'bond_yield_5y': company_data.bond_yield_5y,
                'passed_all_filters': company_data.passed_all_filters,
                'filter_operating_income': company_data.filter_operating_income,
                'filter_net_income': company_data.filter_net_income,
                'filter_revenue_cagr': company_data.filter_revenue_cagr,
                'filter_total_assets_operating_income_ratio': company_data.filter_total_assets_operating_income_ratio,
            }
        )
        
        # 기존 데이터인 경우 업데이트
        if not created:
            company.company_name = company_data.company_name
            company.business_type_code = company_data.business_type_code
            company.business_type_name = company_data.business_type_name
            company.bond_yield_5y = company_data.bond_yield_5y
            company.passed_all_filters = company_data.passed_all_filters
            company.filter_operating_income = company_data.filter_operating_income
            company.filter_net_income = company_data.filter_net_income
            company.filter_revenue_cagr = company_data.filter_revenue_cagr
            company.filter_total_assets_operating_income_ratio = company_data.filter_total_assets_operating_income_ratio
            company.save()
        
        # YearlyFinancialData 모델 저장 또는 업데이트
        for yearly_data in company_data.yearly_data:
            yearly_model, created = YearlyFinancialDataModel.objects.get_or_create(
                company=company,
                year=yearly_data.year,
                defaults={
                    'revenue': yearly_data.revenue,
                    'operating_income': yearly_data.operating_income,
                    'net_income': yearly_data.net_income,
                    'total_assets': yearly_data.total_assets,
                    'total_equity': yearly_data.total_equity,
                    'gross_profit_margin': yearly_data.gross_profit_margin,
                    'selling_admin_expense_ratio': yearly_data.selling_admin_expense_ratio,
                    'total_assets_operating_income_ratio': yearly_data.total_assets_operating_income_ratio,
                    'roe': yearly_data.roe,
                }
            )
            
            # 기존 데이터인 경우 업데이트
            if not created:
                yearly_model.revenue = yearly_data.revenue
                yearly_model.operating_income = yearly_data.operating_income
                yearly_model.net_income = yearly_data.net_income
                yearly_model.total_assets = yearly_data.total_assets
                yearly_model.total_equity = yearly_data.total_equity
                yearly_model.gross_profit_margin = yearly_data.gross_profit_margin
                yearly_model.selling_admin_expense_ratio = yearly_data.selling_admin_expense_ratio
                yearly_model.total_assets_operating_income_ratio = yearly_data.total_assets_operating_income_ratio
                yearly_model.roe = yearly_data.roe
                yearly_model.save()


