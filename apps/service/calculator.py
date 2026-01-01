"""
재무 지표 계산 서비스
"""
import logging
from apps.models import YearlyFinancialDataObject, CompanyFinancialObject

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """재무 지표 계산 서비스"""
    
    # 클래스 상수
    DEFAULT_TAX_RATE = 0.25  # 법인세율 (25%)
    DEFAULT_EQUITY_RISK_PREMIUM = 5.0  # 주주기대수익률 (5%)
    
    @staticmethod
    def calculate_cagr(start_value: float, end_value: float, years: int) -> float:
        """
        CAGR (Compound Annual Growth Rate, 연평균 성장률) 계산
        
        공식: CAGR = (end_value / start_value)^(1/years) - 1
        
        예시: 5년 CAGR의 경우
        - 시작값: 1년차 값
        - 최종값: 5년차 값
        - years: 4 (1년차와 5년차 사이의 간격)
        - CAGR = (5년차 값 / 1년차 값)^(1/4) - 1
        
        Args:
            start_value: 시작값
            end_value: 최종값
            years: 기간 (년수, 시작값과 최종값 사이의 간격)
        
        Returns:
            CAGR (% 단위, float). 계산 불가능한 경우 0.0 반환
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
        
        # 백분율로 변환
        return cagr * 100
    
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
    def calculate_roic(yearly_data: YearlyFinancialDataObject, tax_rate: float = DEFAULT_TAX_RATE) -> float:
        """
        ROIC (Return on Invested Capital, 투하자본수익률) 계산
        
        공식: (영업이익 × (1 - 법인세율)) / (자기자본 + 이자부채 − 현금및현금성자산)
        
        Args:
            yearly_data: YearlyFinancialDataObject 객체
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
        yearly_data: YearlyFinancialDataObject,
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
            yearly_data: YearlyFinancialDataObject 객체
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
        
        주의: XBRL 데이터 수집이 중단되어 계산 지표 계산도 중단되었습니다.
        FCF, ICR, ROIC, WACC 계산에 필요한 데이터(CFO, 금융비용, 자기자본 등)는
        XBRL에서만 수집 가능하며, 표본이 너무 적어서 데이터화를 못할듯하여 일단 중단했습니다.
        
        Args:
            company_data: CompanyFinancialObject 객체
            tax_rate: 법인세율 (기본값: 0.25)
            equity_risk_premium: 주주기대수익률 (기본값: 5.0)
        """
        if not company_data.yearly_data:
            return
        
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
    
    @staticmethod
    def calculate_total_assets_operating_income_ratio(yearly_data: YearlyFinancialDataObject) -> float:
        """
        총자산영업이익률 계산
        
        공식: (영업이익 / 자산총계)
        
        주의: 프론트엔드 formatPercent가 value * 100을 하므로 소수 형태로 저장해야 합니다.
        예: 30.335% -> 0.30335로 저장 (프론트에서 0.30335 * 100 = 30.335%로 표시)
        
        Args:
            yearly_data: YearlyFinancialDataObject 객체
        
        Returns:
            총자산영업이익률 (소수 형태, float, 예: 0.30335 = 30.335%)
        """
        if yearly_data.total_assets > 0:
            return yearly_data.operating_income / yearly_data.total_assets
        return 0.0
    
    @staticmethod
    def calculate_roe(yearly_data: YearlyFinancialDataObject) -> float:
        """
        ROE (Return on Equity, 자기자본수익률) 계산
        
        공식: (당기순이익 / 자본총계)
        
        주의: 프론트엔드 formatPercent가 value * 100을 하므로 소수 형태로 저장해야 합니다.
        예: 15.5% -> 0.155로 저장 (프론트에서 0.155 * 100 = 15.5%로 표시)
        
        Args:
            yearly_data: YearlyFinancialDataObject 객체
        
        Returns:
            ROE (소수 형태, float, 예: 0.155 = 15.5%)
        """
        if yearly_data.total_equity > 0:
            return yearly_data.net_income / yearly_data.total_equity
        return 0.0
    
    @staticmethod
    def calculate_basic_financial_ratios(company_data: CompanyFinancialObject) -> None:
        """
        기본 재무지표 계산 (총자산영업이익률, ROE)
        
        기본 지표 API(fnlttSinglAcnt.json)에서 수집한 데이터로 계산 가능한 재무지표를 계산합니다.
        API 호출 최적화를 위해 재무지표 API 호출을 제거하고 계산 방식으로 변경되었습니다.
        
        Args:
            company_data: CompanyFinancialObject 객체 (in-place 수정)
        """
        for yearly_data in company_data.yearly_data:
            # 총자산영업이익률 계산
            yearly_data.total_assets_operating_income_ratio = (
                IndicatorCalculator.calculate_total_assets_operating_income_ratio(yearly_data)
            )
            
            # ROE 계산
            yearly_data.roe = IndicatorCalculator.calculate_roe(yearly_data)

