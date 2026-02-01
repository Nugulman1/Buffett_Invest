"""
장기 투자 필터링 서비스
"""
from apps.models import CompanyFinancialObject
from apps.service.calculator import IndicatorCalculator

# 최근 5년 중 영업이익 ≤ 0 인 연도 ≤ 1회
# 최근 5년 중 당기순이익 합계 > 0
# 매출액 CAGR ≥ 10%
# 영업이익률 평균 ≥ 10%
# ROE 평균 (규모별): 대기업 ≥ 8%, 중견기업 ≥ 10%, 중소기업 ≥ 12%

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
        
        # 데이터 없음(None)인 연도는 제외
        valid_data = [d for d in data_to_check if d.operating_income is not None]
        if not valid_data:
            return False
        negative_count = sum(1 for d in valid_data if d.operating_income <= 0)
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
        
        # 데이터 없음(None)인 연도는 제외
        valid_data = [d for d in data_to_check if d.net_income is not None]
        if not valid_data:
            return False
        total_net_income = sum(d.net_income for d in valid_data)
        return total_net_income > 0
    
    @staticmethod
    def filter_revenue_cagr(company_data: CompanyFinancialObject) -> bool:
        """
        매출액 CAGR 필터: 매출액 CAGR ≥ 10%
        (5년 데이터가 없어도 수집된 데이터로 계산, 최소 2년 데이터 필요)
        
        Args:
            company_data: CompanyFinancialObject 객체
        
        Returns:
            필터 통과 여부 (bool)
        """
        if not company_data.yearly_data:
            return False
        
        # 데이터 정렬 (오름차순)
        sorted_data = sorted(company_data.yearly_data, key=lambda x: x.year)
        
        # 데이터 없음(None) 또는 0인 연도 제외, revenue > 0인 연도만 사용
        valid_data = [d for d in sorted_data if d.revenue is not None and d.revenue > 0]
        if len(valid_data) < 2:
            return True
        start_value = valid_data[0].revenue
        end_value = valid_data[-1].revenue
        years_span = valid_data[-1].year - valid_data[0].year
        cagr = IndicatorCalculator.calculate_cagr(start_value, end_value, years_span)
        return cagr >= 0.10
    
    @staticmethod
    def filter_operating_margin(company_data: CompanyFinancialObject) -> bool:
        """
        영업이익률 필터: 영업이익률 평균 ≥ 10%
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
        
        # 데이터 없음(None)인 연도는 제외
        ratios = [d.operating_margin for d in data_to_check if d.operating_margin is not None]
        if not ratios:
            return False
        average_ratio = sum(ratios) / len(ratios)
        return average_ratio >= 0.10
    
    @staticmethod
    def filter_roe(company_data: CompanyFinancialObject) -> bool:
        """
        ROE 필터: 기업 규모별 ROE 평균 임계값 적용
        - 대기업 (총자산 ≥ 10조): 평균 ROE ≥ 8%
        - 중견기업 (5천억 ≤ 총자산 < 10조): 평균 ROE ≥ 10%
        - 중소기업 (총자산 < 5천억): 평균 ROE ≥ 12%
        
        (5년 데이터가 없어도 수집된 데이터로 계산)
        
        주의:
        - 총자산은 최신 연도(year가 가장 큰 값) 데이터 사용
        - 자본총계가 0 이하인 연도는 ROE 계산에서 제외
        - 모든 연도가 자본잠식이면 필터 실패 처리
        
        Args:
            company_data: CompanyFinancialObject 객체
        
        Returns:
            필터 통과 여부 (bool)
        """
        if not company_data.yearly_data:
            return False
        
        # 최신 연도 총자산으로 기업 규모 분류 (total_assets가 None이 아닌 연도 사용)
        from apps.utils import classify_company_size
        sorted_data = sorted(company_data.yearly_data, key=lambda x: x.year)
        valid_for_assets = [d for d in reversed(sorted_data) if d.total_assets is not None]
        if not valid_for_assets:
            return False
        latest_total_assets = valid_for_assets[0].total_assets
        company_size = classify_company_size(latest_total_assets)
        
        roe_thresholds = {'large': 0.08, 'medium': 0.10, 'small': 0.12}
        threshold = roe_thresholds[company_size]
        
        data_to_check = sorted_data[-5:] if len(sorted_data) >= 5 else sorted_data
        roe_values = []
        for d in data_to_check:
            if d.total_equity is not None and d.total_equity > 0 and d.roe is not None:
                roe_values.append(d.roe)
        if not roe_values:
            return False
        average_roe = sum(roe_values) / len(roe_values)
        return average_roe >= threshold
    
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
        company_data.filter_operating_margin = cls.filter_operating_margin(company_data)
        company_data.filter_roe = cls.filter_roe(company_data)
        
        # 전체 필터 통과 여부: 모든 필터가 True여야 함
        company_data.passed_all_filters = (
            company_data.filter_operating_income and
            company_data.filter_net_income and
            company_data.filter_revenue_cagr and
            company_data.filter_operating_margin and
            company_data.filter_roe
        )

