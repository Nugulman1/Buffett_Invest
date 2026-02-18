"""
재무 지표 계산 서비스
"""
import logging
from django.conf import settings

from apps.models import YearlyFinancialDataObject, CompanyFinancialObject

logger = logging.getLogger(__name__)


def _get_calculator_tax_rate_decimal():
    """설정의 법인세율(%) → 소수 (0.25)"""
    return settings.CALCULATOR_DEFAULTS['TAX_RATE'] / 100.0


def _get_calculator_equity_risk_premium():
    """설정의 주주기대수익률(%) (5.0 등)"""
    return settings.CALCULATOR_DEFAULTS['EQUITY_RISK_PREMIUM']


class IndicatorCalculator:
    """재무 지표 계산 서비스"""

    @staticmethod
    def calculate_cagr(start_value: float, end_value: float, years: int) -> float:
        """
        CAGR (Compound Annual Growth Rate, 연평균 성장률) 계산
        
        공식: CAGR = (end_value / start_value)^(1/years) - 1
        
        CAGR은 복리 기준 연평균 성장률로, 시작값에서 최종값까지 일정한 연평균 성장률로
        증가했다고 가정했을 때의 성장률을 의미합니다. 중간 연도의 변동을 평활화하여
        전체 기간의 성장 추세를 파악하는 데 사용됩니다.
        
        예시: 5년 CAGR의 경우
        - 시작값: 1년차 값 (예: 2020년 매출액)
        - 최종값: 5년차 값 (예: 2024년 매출액)
        - years: 4 (1년차와 5년차 사이의 간격, 2020~2024는 4년 간격)
        - CAGR = (5년차 값 / 1년차 값)^(1/4) - 1
        
        구체적 계산 예시:
        - 2020년 매출액: 100억원
        - 2024년 매출액: 146.41억원
        - CAGR = (146.41 / 100)^(1/4) - 1 = 1.4641^0.25 - 1 = 1.1 - 1 = 0.1 = 10%
        
        주의사항:
        - 현재 코드에서는 매출액(revenue) 기준으로 사용되지만, 이 함수는 범용 함수로
          어떤 재무 지표(영업이익, 당기순이익, 자산총계 등)에도 적용 가능합니다.
        - years는 시작값과 최종값 사이의 간격이므로, 데이터 개수 - 1입니다.
          예: 2020, 2021, 2022, 2023, 2024 (5개 데이터) → years = 4
        
        Args:
            start_value: 시작값 (첫 년도 값)
            end_value: 최종값 (마지막 년도 값)
            years: 기간 (년수, 시작값과 최종값 사이의 간격)
        
        Returns:
            CAGR (소수 형태, float). 계산 불가능한 경우 0.0 반환
            예: 0.105 = 10.5%의 CAGR
        """
        if start_value <= 0:
            logger.warning(f"CAGR 계산 실패: 시작값이 0 이하입니다 (start_value: {start_value})")
            return 0.0
        
        if end_value < 0:
            logger.warning(f"CAGR 계산 실패: 최종값이 음수입니다 (end_value: {end_value})")
            return 0.0
        
        if years <= 0:
            logger.warning(f"CAGR 계산 실패: 기간이 0 이하입니다 (years: {years})")
            return 0.0
        
        # CAGR 계산: (end_value / start_value)^(1/years) - 1
        ratio = end_value / start_value
        cagr = (ratio ** (1.0 / years)) - 1
        
        # 소수 형태로 반환 (예: 0.10 = 10%)
        return cagr
    
    @staticmethod
    def calculate_fcf(yearly_data: YearlyFinancialDataObject) -> int:
        """
        FCF (Free Cash Flow, 자유현금흐름) 계산
        
        공식: CFO - |유형자산 취득 + 무형자산 취득|
        
        주의: CAPEX는 절대값으로 처리합니다 (음수인 경우 자산 처분 등으로 인한 것)
        
        Args:
            yearly_data: YearlyFinancialDataObject 객체
        
        Returns:
            FCF 값 (정수, 원화)
        """
        capex = yearly_data.tangible_asset_acquisition + yearly_data.intangible_asset_acquisition
        fcf = yearly_data.cfo - abs(capex)
        return fcf
    
    @staticmethod
    def calculate_icr(yearly_data: YearlyFinancialDataObject) -> float:
        """
        ICR (Interest Coverage Ratio, 이자보상비율) 계산
        
        공식: 영업이익 / 금융비용
        
        주의: 이자비용 대신 금융비용을 사용합니다 (간소화 버전).
        금융비용은 이자비용보다 넓은 개념이므로 실제 ICR보다 약간 낮게 나올 수 있습니다.
        현재 사용하지 않습니다.
        
        Args:
            yearly_data: YearlyFinancialDataObject 객체
        
        Returns:
            ICR 값 (배수, float)
        """
        if yearly_data.finance_costs == 0:
            logger.warning(f"ICR 계산 실패: 금융비용이 0입니다 (year: {yearly_data.year})")
            return 0.0
        
        icr = yearly_data.operating_income / yearly_data.finance_costs
        return icr
    
    @staticmethod
    def calculate_roic(yearly_data: YearlyFinancialDataObject, tax_rate: float = None) -> float:
        """
        ROIC (Return on Invested Capital, 투하자본수익률) 계산
        
        공식: (영업이익 × (1 - 법인세율)) / (자기자본 + 이자부채 − 현금및현금성자산)
        
        Args:
            yearly_data: YearlyFinancialDataObject 객체
            tax_rate: 법인세율 소수 (기본값: settings.CALCULATOR_DEFAULTS)
        
        Returns:
            ROIC 값 (소수 형태, float, 예: 0.10 = 10%)
        """
        if tax_rate is None:
            tax_rate = _get_calculator_tax_rate_decimal()
        # 이자부채 (통합 필드 사용)
        interest_bearing_debt = yearly_data.interest_bearing_debt
        
        # 분모 계산: 자기자본 + 이자부채 - 현금및현금성자산
        cash = yearly_data.cash_and_cash_equivalents or 0
        denominator = yearly_data.equity + interest_bearing_debt - cash
        
        if denominator == 0:
            logger.warning(
                f"ROIC 계산 실패: (자기자본 + 이자부채 - 현금및현금성자산)이 0입니다 "
                f"(year: {yearly_data.year}, equity: {yearly_data.equity}, "
                f"interest_bearing_debt: {interest_bearing_debt}, "
                f"cash: {yearly_data.cash_and_cash_equivalents})"
            )
            return 0.0
        
        # 분자: 영업이익 × (1 - 법인세율)
        numerator = yearly_data.operating_income * (1 - tax_rate)
        
        # ROIC 계산 (소수 형태)
        return numerator / denominator

    @staticmethod
    def calculate_invested_capital(yearly_data: YearlyFinancialDataObject) -> int:
        """
        IC (Invested Capital, 투하자본) 계산. ROIC 분모와 동일.

        공식: 자기자본 + 이자부채 - 현금및현금성자산
        """
        cash = yearly_data.cash_and_cash_equivalents or 0
        return yearly_data.equity + yearly_data.interest_bearing_debt - cash

    @staticmethod
    def calculate_ev(
        market_cap: int,
        interest_bearing_debt: int,
        cash: int,
        noncontrolling_interest: int = 0,
    ) -> int:
        """
        EV (Enterprise Value, 기업가치) 계산.

        공식: 시가총액 + 이자부채 - 현금 + 비지배지분
        """
        return market_cap + interest_bearing_debt - cash + noncontrolling_interest

    @staticmethod
    def calculate_wacc(
        yearly_data: YearlyFinancialDataObject,
        bond_yield: float,
        tax_rate: float = None,
        equity_risk_premium: float = None
    ) -> float:
        """
        WACC (Weighted Average Cost of Capital, 가중평균자본비용) 계산
        
        공식: WACC = (E / (E + D)) × Re + (D / (E + D)) × Rd × (1 - 법인세율)
        
        - E = 자기자본 (equity)
        - D = 이자부채 (interest_bearing_debt)
        - Re = 국채수익률 (bond_yield) + 주주기대수익률 (equity_risk_premium)
        - Rd = 이자비용 / 이자부채
        
        Args:
            yearly_data: YearlyFinancialDataObject 객체
            bond_yield: 국채수익률 (퍼센트 형태, 예: 3.5 = 3.5%)
            tax_rate: 법인세율 (기본값: 0.25)
            equity_risk_premium: 주주기대수익률 (퍼센트 형태, 기본값: settings)
        
        Returns:
            WACC 값 (소수 형태, float, 예: 0.10 = 10%)
        """
        if tax_rate is None:
            tax_rate = _get_calculator_tax_rate_decimal()
        if equity_risk_premium is None:
            equity_risk_premium = _get_calculator_equity_risk_premium()

        # E = 자기자본
        equity = yearly_data.equity
        
        # D = 이자부채 (통합 필드 사용)
        interest_bearing_debt = yearly_data.interest_bearing_debt
        
        # E + D가 0이면 계산 불가
        total_capital = equity + interest_bearing_debt
        if total_capital == 0:
            logger.warning(
                f"WACC 계산 실패: (자기자본 + 이자부채)가 0입니다 "
                f"(year: {yearly_data.year}, equity: {equity}, interest_bearing_debt: {interest_bearing_debt})"
            )
            return 0.0
        
        # Re = 국채수익률 + 주주기대수익률 (퍼센트를 소수점으로 변환)
        cost_of_equity = (bond_yield + equity_risk_premium) / 100.0
        
        # Rd = 이자비용 / 이자부채 (비율 형태)
        if interest_bearing_debt == 0:
            # 이자부채가 0이면 부채 부분은 0으로 처리
            cost_of_debt = 0.0
            logger.warning(
                f"WACC 계산: 이자부채가 0입니다 (Rd 계산 불가, year: {yearly_data.year})"
            )
        else:
            cost_of_debt = yearly_data.interest_expense / interest_bearing_debt
        
        # WACC 계산 (소수점 형태로 통일)
        equity_weight = equity / total_capital
        debt_weight = interest_bearing_debt / total_capital
        
        wacc = (equity_weight * cost_of_equity) + (debt_weight * cost_of_debt * (1 - tax_rate))
        
        # 소수 형태로 반환
        return wacc
    
    @classmethod
    def calculate_all_indicators(
        cls,
        company_data: CompanyFinancialObject,
        tax_rate: float = None,
        equity_risk_premium: float = None
    ) -> None:
        """
        모든 계산 지표 채우기
        
        주의: FCF, ROIC, WACC 등에 필요한 추가 데이터(CFO, 유형/무형자산취득 등)는
        현재 수집하지 않아 해당 연도는 계산 생략.
        
        Args:
            company_data: CompanyFinancialObject 객체
            tax_rate: 법인세율 소수 (기본값: settings.CALCULATOR_DEFAULTS)
            equity_risk_premium: 주주기대수익률 % (기본값: settings.CALCULATOR_DEFAULTS)
        """
        if tax_rate is None:
            tax_rate = _get_calculator_tax_rate_decimal()
        if equity_risk_premium is None:
            equity_risk_premium = _get_calculator_equity_risk_premium()
        if not company_data.yearly_data:
            return
    
    @staticmethod
    def calculate_operating_margin(yearly_data: YearlyFinancialDataObject) -> float | None:
        """
        영업이익률 계산
        
        공식: (영업이익 / 매출액)
        
        주의: 프론트엔드 formatPercent가 value * 100을 하므로 소수 형태로 저장해야 합니다.
        예: 10.5% -> 0.105로 저장 (프론트에서 0.105 * 100 = 10.5%로 표시)
        
        Args:
            yearly_data: YearlyFinancialDataObject 객체
        
        Returns:
            영업이익률 (소수 형태, float, 예: 0.105 = 10.5%). 데이터 없으면 None
        """
        if yearly_data.revenue is None or yearly_data.revenue <= 0:
            return None
        oi = yearly_data.operating_income
        if oi is None:
            return None
        return oi / yearly_data.revenue

    @staticmethod
    def calculate_debt_ratio(yearly_data: YearlyFinancialDataObject) -> float | None:
        """
        부채비율 계산 (총자본/부채총계)

        공식: 자본총계 / 부채총계
        부채총계가 0이거나 없으면 계산하지 않음 (None 반환).

        Args:
            yearly_data: YearlyFinancialDataObject 객체

        Returns:
            부채비율 (float). 데이터 없거나 부채총계 0이면 None
        """
        total_equity = yearly_data.total_equity
        total_liabilities = getattr(yearly_data, 'total_liabilities', None)
        if total_liabilities is None or total_liabilities <= 0:
            return None
        if total_equity is None:
            return None
        return total_equity / total_liabilities

    @staticmethod
    def calculate_basic_financial_ratios(company_data: CompanyFinancialObject) -> None:
        """
        기본 재무지표 계산 (영업이익률, 부채비율)
        
        영업이익률은 기본 지표(매출액·영업이익)로 계산. ROE는 DART 주요재무지표 M211550에서 채움.
        부채비율은 자본총계/부채총계.
        
        Args:
            company_data: CompanyFinancialObject 객체 (in-place 수정)
        """
        for yearly_data in company_data.yearly_data:
            yearly_data.operating_margin = (
                IndicatorCalculator.calculate_operating_margin(yearly_data)
            )
            yearly_data.debt_ratio = IndicatorCalculator.calculate_debt_ratio(yearly_data)
    
    @staticmethod
    def calculate_basic_financial_ratios_for_quarterly(quarterly_data: 'YearlyFinancialDataObject') -> None:
        """
        분기보고서용 기본 재무지표 계산 (영업이익률만)
        
        YearlyFinancialDataObject를 분기 데이터로도 사용하므로 동일한 계산 함수 사용
        분기보고서에서는 ROE를 계산하지 않음
        
        Args:
            quarterly_data: YearlyFinancialDataObject 객체 (분기 데이터용, in-place 수정)
        """
        # 영업이익률 계산
        quarterly_data.operating_margin = IndicatorCalculator.calculate_operating_margin(quarterly_data)
        
        # ROE는 분기보고서에서 계산하지 않음

