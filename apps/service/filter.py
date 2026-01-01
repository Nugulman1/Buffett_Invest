"""
장기 투자 필터링 서비스
"""
import logging
from apps.models import CompanyFinancialObject
from apps.service.calculator import IndicatorCalculator

logger = logging.getLogger(__name__)


class CompanyFilter:
    """장기 투자 필터링 서비스"""
    
    @staticmethod
    def filter_operating_income(company_data: CompanyFinancialObject) -> bool:
        """
        영업이익 필터: 최근 5년 중 영업이익 ≤ 0 인 연도 ≤ 1회
        (5년 데이터가 없어도 수집된 데이터로 계산)
        
        Args:
            company_data: CompanyFinancialObject 객체
        
        Returns:
            필터 통과 여부 (bool)
        """
        if not company_data.yearly_data:
            return False
        
        # 데이터 정렬 (오름차순)
        sorted_data = sorted(company_data.yearly_data, key=lambda x: x.year)
        
        # 최근 5년 또는 모든 데이터 사용 (5년 미만인 경우)
        data_to_check = sorted_data[-5:] if len(sorted_data) >= 5 else sorted_data
        
        # 영업이익 ≤ 0 인 연도 개수 계산
        negative_count = sum(1 for data in data_to_check if data.operating_income <= 0)
        
        # 영업이익 ≤ 0 인 연도가 1회 이하인지 확인
        return negative_count <= 1
    
    @staticmethod
    def filter_net_income(company_data: CompanyFinancialObject) -> bool:
        """
        당기순이익 필터: 최근 5년 당기순이익 합계 > 0
        (5년 데이터가 없어도 수집된 데이터로 계산)
        
        Args:
            company_data: CompanyFinancialObject 객체
        
        Returns:
            필터 통과 여부 (bool)
        """
        if not company_data.yearly_data:
            return False
        
        # 데이터 정렬 (오름차순)
        sorted_data = sorted(company_data.yearly_data, key=lambda x: x.year)
        
        # 최근 5년 또는 모든 데이터 사용 (5년 미만인 경우)
        data_to_check = sorted_data[-5:] if len(sorted_data) >= 5 else sorted_data
        
        # 당기순이익 합계 계산
        total_net_income = sum(data.net_income for data in data_to_check)
        
        # 합계가 0보다 큰지 확인
        return total_net_income > 0
    
    @staticmethod
    def filter_revenue_cagr(company_data: CompanyFinancialObject) -> bool:
        """
        매출액 CAGR 필터: 매출액 CAGR ≥ 0%
        (5년 데이터가 없어도 수집된 데이터로 계산, 최소 2년 데이터 필요)
        
        단, 금융업인 경우 자동으로 True 반환 (금융업은 매출액 개념이 다름)
        
        Args:
            company_data: CompanyFinancialObject 객체
        
        Returns:
            필터 통과 여부 (bool)
        """
        # 금융업인 경우 자동으로 True 반환
        from apps.utils.utils import is_financial_industry
        if is_financial_industry(company_data.business_type_code):
            logger.info(f"금융업으로 판별되어 매출액 CAGR 필터를 자동 통과 처리합니다.")
            return True
        
        if not company_data.yearly_data:
            return False
        
        # 데이터 정렬 (오름차순)
        sorted_data = sorted(company_data.yearly_data, key=lambda x: x.year)
        
        # 최소 2년 데이터 필요 (CAGR 계산을 위해)
        if len(sorted_data) < 2:
            return True
        
        # 시작값 (첫 년도)과 최종값 (마지막 년도)
        start_value = sorted_data[0].revenue
        end_value = sorted_data[-1].revenue
        years_span = len(sorted_data) - 1  # 첫 년도와 마지막 년도 사이의 간격
        
        # CAGR 계산
        cagr = IndicatorCalculator.calculate_cagr(start_value, end_value, years_span)
        
        # CAGR ≥ 0% 인지 확인
        return cagr >= 0.0
    
    @staticmethod
    def filter_total_assets_operating_income_ratio(company_data: CompanyFinancialObject) -> bool:
        """
        총자산영업이익률 필터: 총자산영업이익률 평균 > 0
        (5년 데이터가 없어도 수집된 데이터로 계산)
        
        Args:
            company_data: CompanyFinancialObject 객체
        
        Returns:
            필터 통과 여부 (bool)
        """
        if not company_data.yearly_data:
            return False
        
        # 데이터 정렬 (오름차순)
        sorted_data = sorted(company_data.yearly_data, key=lambda x: x.year)
        
        # 최근 5년 또는 모든 데이터 사용 (5년 미만인 경우)
        data_to_check = sorted_data[-5:] if len(sorted_data) >= 5 else sorted_data
        
        # 총자산영업이익률 평균 계산
        ratios = [data.total_assets_operating_income_ratio for data in data_to_check]
        average_ratio = sum(ratios) / len(ratios) if ratios else 0.0
        
        # 평균이 0보다 큰지 확인
        return average_ratio > 0.0
    
    @classmethod
    def apply_all_filters(cls, company_data: CompanyFinancialObject) -> None:
        """
        모든 필터를 적용하고 결과를 CompanyFinancialObject에 저장
        
        하나라도 false면 passed_all_filters를 false로 설정합니다.
        
        Args:
            company_data: CompanyFinancialObject 객체 (in-place 수정)
        """
        # 각 필터 적용
        company_data.filter_operating_income = cls.filter_operating_income(company_data)
        company_data.filter_net_income = cls.filter_net_income(company_data)
        company_data.filter_revenue_cagr = cls.filter_revenue_cagr(company_data)
        company_data.filter_total_assets_operating_income_ratio = cls.filter_total_assets_operating_income_ratio(company_data)
        
        # 전체 필터 통과 여부: 모든 필터가 True여야 함
        company_data.passed_all_filters = (
            company_data.filter_operating_income and
            company_data.filter_net_income and
            company_data.filter_revenue_cagr and
            company_data.filter_total_assets_operating_income_ratio
        )

