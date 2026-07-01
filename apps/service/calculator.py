"""
재무 지표 계산 서비스
"""
import logging
import math

from django.conf import settings

from apps.models import YearlyFinancialDataObject, CompanyFinancialObject

logger = logging.getLogger(__name__)


def _get_calculator_tax_rate_decimal():
    """설정의 법인세율(%) → 소수 (0.25)"""
    return settings.CALCULATOR_DEFAULTS['TAX_RATE'] / 100.0


def _get_calculator_equity_risk_premium():
    """설정의 주주기대수익률(%) (5.0 등)"""
    return settings.CALCULATOR_DEFAULTS['EQUITY_RISK_PREMIUM']


def _get_wacc_equity_premium_buffer():
    """설정의 WACC 자기자본비용 보수 가산(%p, 기본 0.5)"""
    return settings.CALCULATOR_DEFAULTS.get('WACC_EQUITY_PREMIUM_BUFFER', 0.5)


class IndicatorCalculator:
    """재무 지표 계산 서비스"""

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

        공식: 시가총액 + 이자부채 - 기말현금및현금성자산 + 비지배지분
        현금은 표준 정의대로 전액 차감 (ROIC/IC 분모와 동일하게 통일 — T5).
        주: 운용현금/초과현금 구분(초과현금만 차감)은 후순위 정교화 과제.
        """
        return market_cap + interest_bearing_debt - cash + noncontrolling_interest

    @staticmethod
    def compute_ic_ev(
        yearly_data: YearlyFinancialDataObject,
        market_cap: int | None,
    ) -> tuple[int | None, int | None]:
        """
        IC(투하자본)와 EV(기업가치)를 한 번에 계산. (ic, ev) 반환.

        이자부채0/None = 미포착 의심(셀트리온형: 차입금을 '금융부채' 등으로 뭉뚱그려 못 잡았거나
        진짜 무차입) → IC/EV가 왜곡되므로 둘 다 None. 수집 경로(_fill_advanced_indicators)와
        재계산 저장 경로(recompute_and_save_ev_ic)가 같은 정책을 갖도록 이 단일 진실원에 가드를 둔다.
        그 외엔 IC는 항상 계산, EV는 market_cap이 있을 때만 계산하고 없으면 None.
        EV/IC를 계산하는 모든 경로(배치 자동수집 orchestrator, calculate_ev_ic 뷰)가
        이 한 함수를 쓰도록 단일화(T7) — 입력(이자부채·현금·비지배지분) 정의를 한곳에서 보장.
        """
        if not yearly_data.interest_bearing_debt:
            return None, None
        ic = IndicatorCalculator.calculate_invested_capital(yearly_data)
        ev = None
        if market_cap is not None:
            ev = IndicatorCalculator.calculate_ev(
                market_cap,
                yearly_data.interest_bearing_debt,
                yearly_data.cash_and_cash_equivalents,
                yearly_data.noncontrolling_interest,
            )
        return ic, ev

    @staticmethod
    def flag_no_debt_suspect(yearly_data) -> tuple[bool, str]:
        """
        회사 단위 '무차입 의심'(셀트리온형 전수 미포착) 판정.

        compute_ic_ev의 가드는 '연도별'(그 해 이자부채 0/None이면 IC/EV None)만 본다.
        이 함수는 '모든(≥1개) 연도의 이자부채가 0 또는 None'인 **회사 단위** 의심을 판정한다.
        0/None = falsy(미포착/무차입쪽)로 보는 compute_ic_ev의 정책과 일관되게 처리한다 —
        이자부채 정책의 단일 진실원.

        판정:
          - 레코드 0건            → (False, 판정 불가/데이터 없음)
          - ≥1건 & 모든 연도 0/None → (True, 무차입 의심)
          - 양수가 한 연도라도 있음  → (False, 무차입 의심 아님)
        단일 연도(1건)는 flag=True여도 신뢰도가 낮으므로 사유에 연도 수 단서를 노출한다.

        Args:
            yearly_data: .interest_bearing_debt 속성을 노출하는 연간 레코드의 iterable.
                         (속성이 없으면 None으로 간주)

        Returns:
            (무차입_의심_여부, 사유 문자열)
        """
        records = list(yearly_data)
        n = len(records)

        if n == 0:
            return False, '연간 재무데이터가 없어 무차입 의심 판정 불가(데이터 0건)'

        # 0/None = falsy(미포착/무차입쪽). 0/None이 아닌 값(음수 포함)이 하나라도 있으면
        # 전 연도 0/None이 아니므로 의심 아님. (음수도 truthy라 여기 잡힌다 — 사유 문구는
        # '양수'가 아니라 '0/None이 아닌'으로 적어 사실과 일치시킨다.)
        has_nonzero_debt = any(
            getattr(rec, 'interest_bearing_debt', None) for rec in records
        )

        if has_nonzero_debt:
            return False, f'0/None이 아닌 이자부채 연도가 있어 무차입 의심 아님(연도 수 {n})'

        # 모든 연도 이자부채 0/None → 무차입 의심
        if n == 1:
            return True, (
                '단일 연도(1개)만 이자부채 0/None — 무차입 의심이나 '
                '연도 수 1로 신뢰도 낮음'
            )
        return True, f'전 연도({n}개) 이자부채가 0/None이라 무차입 의심'

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
        - Re = 국채수익률 (bond_yield) + 0.5%p(보수적 가산) + 주주기대수익률 (equity_risk_premium)
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
        
        # Re = 국채수익률 + 보수가산(%p) + 주주기대수익률 (퍼센트를 소수점으로 변환)
        buffer = _get_wacc_equity_premium_buffer()
        cost_of_equity = (bond_yield + buffer + equity_risk_premium) / 100.0
        
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
        부채비율 계산 (표준: 부채총계 / 자본총계)

        공식: 부채총계 / 자본총계
        값이 클수록 부채 의존도가 높음(위험). 자본총계가 0 이하(자본잠식)이거나
        없으면 계산하지 않음 (None 반환). 부채총계 0(무차입)은 0.0으로 유효.

        Args:
            yearly_data: YearlyFinancialDataObject 객체

        Returns:
            부채비율 (float). 부채총계 없거나 자본총계 0 이하면 None
        """
        total_equity = yearly_data.total_equity
        total_liabilities = getattr(yearly_data, 'total_liabilities', None)
        if total_liabilities is None:
            return None
        if total_equity is None or total_equity <= 0:
            return None
        return total_liabilities / total_equity

    @staticmethod
    def calculate_g(yearly_data: YearlyFinancialDataObject) -> float | None:
        """
        지속가능성장률 g = ROIC × 유보율(b) 계산.

        - 배당성향(payout) = dividend_paid / net_income
        - 유보율 b = 1 − payout, b를 [0, 1] 구간으로 클램프(과배당·음의배당 방어)
        - g = roic × b

        None 처리:
        - roic None → None (성장률 산출 근거 없음)
        - net_income None 또는 ≤ 0 → None (배당성향 정의 불가/적자)
        - dividend_paid None → 배당성향 0 으로 간주(b=1.0, g=roic)

        Returns:
            g (소수). 산출 불가 시 None
        """
        roic = yearly_data.roic
        if roic is None:
            return None
        net_income = yearly_data.net_income
        if net_income is None or net_income <= 0:
            return None
        dividend_paid = yearly_data.dividend_paid
        payout = 0.0 if dividend_paid is None else dividend_paid / net_income
        b = 1.0 - payout
        # 유보율을 [0, 1]로 클램프
        b = max(0.0, min(1.0, b))
        return roic * b

    @staticmethod
    def calculate_altman_z_double_prime(yearly_data: YearlyFinancialDataObject) -> float | None:
        """
        Altman Z''-Score (1995, 비제조·신흥시장용 4변수 모형) 계산.

        Z'' = 3.25 + 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4
          X1 = (유동자산 − 유동부채) / 자산총계
          X2 = 이익잉여금 / 자산총계
          X3 = 영업이익 / 자산총계
          X4 = 자본총계 / 부채총계

        None 처리:
        - total_assets None 또는 ≤ 0 → None (분모 무효)
        - total_liabilities None 또는 ≤ 0 → None (X4 분모 무효)
        - current_assets·current_liabilities·retained_earnings·operating_income·
          total_equity 중 하나라도 None → None

        Returns:
            Z'' 점수 (float). 산출 불가 시 None
        """
        total_assets = yearly_data.total_assets
        if total_assets is None or total_assets <= 0:
            return None
        total_liabilities = yearly_data.total_liabilities
        if total_liabilities is None or total_liabilities <= 0:
            return None
        current_assets = yearly_data.current_assets
        current_liabilities = yearly_data.current_liabilities
        retained_earnings = yearly_data.retained_earnings
        operating_income = yearly_data.operating_income
        total_equity = yearly_data.total_equity
        if None in (current_assets, current_liabilities, retained_earnings,
                    operating_income, total_equity):
            return None

        x1 = (current_assets - current_liabilities) / total_assets
        x2 = retained_earnings / total_assets
        x3 = operating_income / total_assets
        x4 = total_equity / total_liabilities
        return 3.25 + 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4

    @staticmethod
    def calculate_zmijewski(yearly_data: YearlyFinancialDataObject) -> float | None:
        """
        Zmijewski (1984) 부실확률 계산.

        X = −4.336 − 4.513·(net_income/total_assets)
                  + 5.679·(total_liabilities/total_assets)
                  + 0.004·(current_assets/current_liabilities)
        P = 1 / (1 + e^(−X))

        None 처리:
        - total_assets None 또는 ≤ 0 → None (분모 무효)
        - net_income None → None
        - total_liabilities None → None
        - current_assets None → None
        - current_liabilities None 또는 ≤ 0 → None (유동비율 분모 무효)

        Returns:
            부실확률 P (0~1, float). 산출 불가 시 None
        """
        total_assets = yearly_data.total_assets
        if total_assets is None or total_assets <= 0:
            return None
        net_income = yearly_data.net_income
        if net_income is None:
            return None
        total_liabilities = yearly_data.total_liabilities
        if total_liabilities is None:
            return None
        current_assets = yearly_data.current_assets
        if current_assets is None:
            return None
        current_liabilities = yearly_data.current_liabilities
        if current_liabilities is None or current_liabilities <= 0:
            return None

        roa = net_income / total_assets
        leverage = total_liabilities / total_assets
        liquidity = current_assets / current_liabilities
        x = -4.336 - 4.513 * roa + 5.679 * leverage + 0.004 * liquidity
        return 1.0 / (1.0 + math.exp(-x))

    @staticmethod
    def classify_altman_z(z: float | None) -> str | None:
        """
        Altman Z'' 점수를 부실등급으로 분류.

        - None → None
        - z ≥ 2.6           → 'safe'
        - 1.1 ≤ z < 2.6     → 'grey'
        - z < 1.1           → 'distress'
        """
        if z is None:
            return None
        if z >= 2.6:
            return 'safe'
        if z >= 1.1:
            return 'grey'
        return 'distress'

    @staticmethod
    def flag_zmijewski(prob: float | None) -> bool | None:
        """
        Zmijewski 부실확률 경보 플래그.

        - None → None
        - prob ≥ 0.5 → True (부실 경보)
        - 그 외      → False
        """
        if prob is None:
            return None
        return prob >= 0.5

    @staticmethod
    def fill_valuation_indicators(yearly_data) -> None:
        """
        내재가치 5선 지표를 yd에 in-place 세팅(반환 None).

        기존 검증된 calculate_*/classify/flag 함수들을 조합해 5속성을 채운다.
        - sustainable_growth = calculate_g(yd)
        - altman_z           = calculate_altman_z_double_prime(yd)
        - altman_z_class     = classify_altman_z(altman_z)
        - zmijewski          = calculate_zmijewski(yd)
        - zmijewski_flag     = flag_zmijewski(zmijewski)

        yd는 속성 접근/세팅만 하면 되므로 YearlyFinancialDataObject와
        YearlyFinancialData(DB 모델 인스턴스) 둘 다에 동작(duck typing).
        입력이 부족한 지표는 각 calculate_* 정책에 따라 None으로 남는다.
        """
        yearly_data.sustainable_growth = IndicatorCalculator.calculate_g(yearly_data)
        yearly_data.altman_z = IndicatorCalculator.calculate_altman_z_double_prime(
            yearly_data
        )
        yearly_data.altman_z_class = IndicatorCalculator.classify_altman_z(
            yearly_data.altman_z
        )
        yearly_data.zmijewski = IndicatorCalculator.calculate_zmijewski(yearly_data)
        yearly_data.zmijewski_flag = IndicatorCalculator.flag_zmijewski(
            yearly_data.zmijewski
        )

    @staticmethod
    def flag_fcf_negative(yearly_data_list, lookback: int = 3,
                          min_negative: int = 2) -> tuple[bool, str]:
        """
        최근 lookback개 연도 중 음의 FCF가 min_negative회 이상이면 경보.

        절차:
        1) year 내림차순 정렬 후 최근 lookback개만 잘라낸다(윈도우 고정).
        2) 그 윈도우 안에서 fcf가 None 아닌 레코드만 모은다.
        3) fcf < 0 개수가 min_negative 이상이면 (True, 사유), 아니면 (False, 사유).
        레코드 0건 또는 유효 fcf 0건이면 (False, 데이터 없음 취지 사유).

        Args:
            yearly_data_list: .year, .fcf 속성을 노출하는 연간 레코드 iterable
            lookback: 최근 몇 개 연도를 볼지 (기본 3)
            min_negative: 음의 FCF 몇 회 이상이면 경보 (기본 2)

        Returns:
            (음의FCF_경보_여부, 사유 문자열)
        """
        records = list(yearly_data_list)
        if not records:
            return False, 'FCF 연간 레코드가 없어 음의 FCF 경보 판정 불가(데이터 0건)'

        # year 내림차순 정렬 후 최근 lookback개를 먼저 자른다
        sorted_recs = sorted(records, key=lambda r: r.year, reverse=True)
        window = sorted_recs[:lookback]

        valid_fcfs = [r.fcf for r in window if r.fcf is not None]
        if not valid_fcfs:
            return False, f'최근 {lookback}년 윈도우에 유효한 FCF가 없어 판정 불가'

        negative_count = sum(1 for f in valid_fcfs if f < 0)
        if negative_count >= min_negative:
            return True, (
                f'최근 {lookback}년 중 유효 FCF {len(valid_fcfs)}개에서 '
                f'음의 FCF {negative_count}회(≥{min_negative}) — 음의 FCF 경보'
            )
        return False, (
            f'최근 {lookback}년 중 유효 FCF {len(valid_fcfs)}개에서 '
            f'음의 FCF {negative_count}회(<{min_negative}) — 경보 아님'
        )

    @staticmethod
    def count_consecutive_dividend_years(yearly_data) -> int:
        """
        최신 연도부터 역순으로 연속 배당 연수를 센다.

        절차: year 내림차순 정렬 후 최신부터 순회. dividend_paid가 None이거나
        0 이하면 즉시 중단(그 이전 연도에 배당이 있어도 무시). 0 초과면 +1.

        Args:
            yearly_data: .year, .dividend_paid 속성을 노출하는 연간 레코드 iterable.

        Returns:
            연속 배당 연수 (int, 0 이상)
        """
        sorted_data = sorted(yearly_data, key=lambda x: x.year, reverse=True)
        count = 0
        for yd in sorted_data:
            if yd.dividend_paid is None or yd.dividend_paid <= 0:
                break
            count += 1
        return count

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

