"""
재무 지표 계산 서비스
"""
import logging
from apps.models import YearlyFinancialData, CompanyFinancialObject

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """재무 지표 계산 서비스"""
    
    # 클래스 상수
    DEFAULT_TAX_RATE = 0.25  # 법인세율 (25%)
    DEFAULT_EQUITY_RISK_PREMIUM = 5.0  # 주주기대수익률 (5%)
    
    @staticmethod
    def calculate_fcf(yearly_data: YearlyFinancialData) -> int:
        """
        FCF (Free Cash Flow, 자유현금흐름) 계산
        
        공식: CFO - |유형자산 취득 + 무형자산 취득|
        
        주의: CAPEX는 절대값으로 처리합니다 (음수인 경우 자산 처분 등으로 인한 것)
        
        Args:
            yearly_data: YearlyFinancialData 객체
        
        Returns:
            FCF 값 (정수, 원화)
        """
        capex = yearly_data.tangible_asset_acquisition + yearly_data.intangible_asset_acquisition
        fcf = yearly_data.cfo - abs(capex)
        return fcf
    
    # @staticmethod
    # def calculate_icr(yearly_data: YearlyFinancialData) -> float:
    #     """
    #     ICR (Interest Coverage Ratio, 이자보상비율) 계산
    #     
    #     공식: 영업이익 / 이자비용
    #     
    #     Args:
    #         yearly_data: YearlyFinancialData 객체
    #     
    #     Returns:
    #         ICR 값 (배수, float)
    #     """
    #     # TODO: 이자비용은 ACODE로 구하지 못하므로 수동 체크 필요
    #     if yearly_data.interest_expense == 0:
    #         logger.warning(f"ICR 계산 실패: 이자비용이 0입니다 (year: {yearly_data.year})")
    #         return 0.0
    #     
    #     icr = yearly_data.operating_income / yearly_data.interest_expense
    #     return icr
    
    @staticmethod
    def calculate_roic(yearly_data: YearlyFinancialData, tax_rate: float = DEFAULT_TAX_RATE) -> float:
        """
        ROIC (Return on Invested Capital, 투하자본수익률) 계산
        
        공식: (영업이익 × (1 - 법인세율)) / (자기자본 + 이자부채 − 현금및현금성자산)
        
        Args:
            yearly_data: YearlyFinancialData 객체
            tax_rate: 법인세율 (기본값: 0.25)
        
        Returns:
            ROIC 값 (% 단위, float)
        """
        # 이자부채 계산
        interest_bearing_debt = (
            yearly_data.short_term_borrowings +
            yearly_data.current_portion_of_long_term_borrowings +
            yearly_data.long_term_borrowings +
            yearly_data.bonds +
            yearly_data.lease_liabilities
        )
        
        # 분모 계산: 자기자본 + 이자부채 - 현금및현금성자산
        denominator = yearly_data.equity + interest_bearing_debt - yearly_data.cash_and_cash_equivalents
        
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
        
        # ROIC 계산 (백분율로 변환)
        roic = (numerator / denominator) * 100
        return roic
    
    @staticmethod
    def calculate_wacc(
        yearly_data: YearlyFinancialData,
        bond_yield: float,
        tax_rate: float = DEFAULT_TAX_RATE,
        equity_risk_premium: float = DEFAULT_EQUITY_RISK_PREMIUM
    ) -> float:
        """
        WACC (Weighted Average Cost of Capital, 가중평균자본비용) 계산
        
        공식: WACC = (E / (E + D)) × Re + (D / (E + D)) × Rd × (1 - 법인세율)
        
        - E = 자기자본 (equity)
        - D = 이자부채 (단기차입금 + 유동성장기차입금 + 장기차입금 + 사채 + 리스부채)
        - Re = 국채수익률 (bond_yield) + 주주기대수익률 (equity_risk_premium)
        - Rd = 금융비용 / 이자부채
        
        주의: 이자비용 대신 금융비용을 사용합니다.
        금융비용은 이자비용보다 넓은 개념이므로, ROIC와 WACC를 비교할 때는
        ROIC에 가산 수치를 넣어야 합니다 (금융비용 - 이자비용 차이).
        
        Args:
            yearly_data: YearlyFinancialData 객체
            bond_yield: 국채수익률 (퍼센트 형태, 예: 3.5 = 3.5%)
            tax_rate: 법인세율 (기본값: 0.25)
            equity_risk_premium: 주주기대수익률 (퍼센트 형태, 기본값: 5.0)
        
        Returns:
            WACC 값 (% 단위, float)
        """
        # E = 자기자본
        equity = yearly_data.equity
        
        # D = 이자부채
        interest_bearing_debt = (
            yearly_data.short_term_borrowings +
            yearly_data.current_portion_of_long_term_borrowings +
            yearly_data.long_term_borrowings +
            yearly_data.bonds +
            yearly_data.lease_liabilities
        )
        
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
        
        # Rd = 금융비용 / 이자부채 (비율 형태)
        # 주의: 이자비용 대신 금융비용을 사용 (ROIC와 비교 시 가산 수치 필요)
        if interest_bearing_debt == 0:
            # 이자부채가 0이면 부채 부분은 0으로 처리
            cost_of_debt = 0.0
            logger.warning(
                f"WACC 계산: 이자부채가 0입니다 (Rd 계산 불가, year: {yearly_data.year})"
            )
        else:
            cost_of_debt = yearly_data.finance_costs / interest_bearing_debt
        
        # WACC 계산 (소수점 형태로 통일)
        equity_weight = equity / total_capital
        debt_weight = interest_bearing_debt / total_capital
        
        wacc = (equity_weight * cost_of_equity) + (debt_weight * cost_of_debt * (1 - tax_rate))
        
        # 백분율로 변환하여 반환
        return wacc * 100
    
    @classmethod
    def calculate_all_indicators(
        cls,
        company_data: CompanyFinancialObject,
        tax_rate: float = DEFAULT_TAX_RATE,
        equity_risk_premium: float = DEFAULT_EQUITY_RISK_PREMIUM
    ) -> None:
        """
        모든 계산 지표 채우기
        
        Args:
            company_data: CompanyFinancialObject 객체
            tax_rate: 법인세율 (기본값: 0.25)
            equity_risk_premium: 주주기대수익률 (기본값: 5.0)
        """
        for yearly_data in company_data.yearly_data:
            # FCF 계산
            yearly_data.fcf = cls.calculate_fcf(yearly_data)
            
            # ICR 계산 (주석처리: 이자비용은 ACODE로 구하지 못하므로 수동 체크 필요)
            # yearly_data.icr = cls.calculate_icr(yearly_data)
            
            # ROIC 계산
            yearly_data.roic = cls.calculate_roic(yearly_data, tax_rate)
            
            # WACC 계산
            yearly_data.wacc = cls.calculate_wacc(
                yearly_data,
                company_data.bond_yield_5y,
                tax_rate,
                equity_risk_premium
            )

