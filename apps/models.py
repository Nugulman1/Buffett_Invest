"""
재무제표 데이터 모델
"""


class FinancialStatementData:
    """연도별 재무제표 데이터 (O(1) 조회용 인덱싱 포함)"""
    
    def __init__(self, year, reprt_code, fs_div, raw_data):
        """
        Args:
            year: 사업연도 (예: '2023')
            reprt_code: 보고서 코드 (11011: 사업보고서)
            fs_div: 재무제표 구분 (CFS: 연결, OFS: 별도)
            raw_data: 원본 재무제표 데이터 리스트 (인덱싱용, 저장하지 않음)
        """
        # 순환 import 방지를 위해 함수 내부에서 lazy import
        from apps.utils.utils import normalize_account_name
        
        self.year = year
        self.reprt_code = reprt_code
        self.fs_div = fs_div
        
        # O(1) 조회를 위한 인덱싱 (계정명을 키로, 값만 저장)
        self.account_index = {}
        # 정규화된 계정명 인덱스 (O(1) 조회용)
        self.normalized_account_index = {}
        
        for item in raw_data:
            account_nm = item.get('account_nm', '')
            if account_nm:
                # 이미 같은 계정명이 있으면 덮어쓰지 않음 (CFS 우선)
                if account_nm not in self.account_index:
                    account_data = {
                        'original_key': account_nm,
                        'thstrm_amount': item.get('thstrm_amount', '0'),
                        'frmtrm_amount': item.get('frmtrm_amount', '0'),
                        'bfefrmtrm_amount': item.get('bfefrmtrm_amount', '0'),
                    }
                    self.account_index[account_nm] = {
                        'thstrm_amount': account_data['thstrm_amount'],
                        'frmtrm_amount': account_data['frmtrm_amount'],
                        'bfefrmtrm_amount': account_data['bfefrmtrm_amount'],
                    }
                    
                    # 정규화된 계정명으로 인덱스 생성 (CFS 우선 유지)
                    normalized_key = normalize_account_name(account_nm)
                    if normalized_key not in self.normalized_account_index:
                        self.normalized_account_index[normalized_key] = account_data
    
    def get_account_value(self, account_name, amount_type='thstrm_amount'):
        """
        계정값 추출 (O(1) 조회)
        
        Args:
            account_name: 계정명 (정확히 일치)
            amount_type: 금액 타입 ('thstrm_amount', 'frmtrm_amount' 등)
        
        Returns:
            계정값 (정수, 없으면 0)
        """
        if account_name in self.account_index:
            amount = self.account_index[account_name].get(amount_type, '0')
            return int(amount.replace(',', '')) if amount else 0
        return 0


class YearlyFinancialData:
    """년도별 재무 데이터 객체"""
    
    def __init__(self, year: int, corp_code: str = ""):
        """
        Args:
            year: 사업연도
            corp_code: 고유번호 (8자리)
        """
        # 회사 정보
        self.year: int = year
        self.corp_code: str = corp_code
        
        # === 기본 지표 (DART API) ===
        self.revenue: int = 0  # 매출액 (5Y)
        self.operating_income: int = 0  # 영업이익 (5Y)
        self.net_income: int = 0  # 당기순이익 (5Y)
        self.total_assets: int = 0  # 자산총계
        self.total_equity: int = 0  # 자본총계
        self.gross_profit_margin: float = 0.0  # 매출총이익률 (%)
        self.selling_admin_expense_ratio: float = 0.0  # 판관비율 (%)
        self.total_assets_operating_income_ratio: float = 0.0  # 총자산영업이익률 (%)
        self.roe: float = 0.0  # ROE (%)
        
        # === 계산에 사용하는 기본 지표 ===
        self.finance_costs: int = 0  # 금융비용 (WACC 계산에 사용)
        self.tangible_asset_acquisition: int = 0  # 유형자산 취득
        self.intangible_asset_acquisition: int = 0  # 무형자산 취득
        self.cfo: int = 0  # 영업활동현금흐름
        self.equity: int = 0  # 자기자본
        self.cash_and_cash_equivalents: int = 0  # 현금및현금성자산
        self.short_term_borrowings: int = 0  # 단기차입금
        self.current_portion_of_long_term_borrowings: int = 0  # 유동성장기차입금
        self.long_term_borrowings: int = 0  # 장기차입금
        self.bonds: int = 0  # 사채
        self.lease_liabilities: int = 0  # 리스부채
        
        # === 현재 계산에 사용하지 않는 지표 ===
        # (향후 계산 공식 변경 시 사용 가능, 데이터 수집은 계속 진행)
        self.current_liabilities: int = 0  # 유동부채
        self.interest_bearing_current_liabilities: int = 0  # 이자부유동부채
        self.interest_expense: int = 0  # 이자비용 (사용 안 함, 금융비용으로 대체됨)
        self.beta: float = 1.0  # 베타 (고정)
        self.mrp: float = 5.0  # MRP (고정)
        
        # 계산된 지표
        self.fcf: int = 0  # 자유현금흐름
        self.icr: float = 0.0  # 이자보상비율 (ratio)
        self.roic: float = 0.0  # 투하자본수익률 (%)
        self.wacc: float = 0.0  # 가중평균자본비용 (%)


class CompanyFinancialObject:
    """회사 재무제표 데이터 객체"""
    
    def __init__(self):
        # 회사 정보
        self.company_name: str = ""
        self.business_type_code: str = ""
        self.business_type_name: str = ""
        self.corp_code: str = ""
        self.bond_yield_5y: float = 0.0  # 채권수익률 (국채 5년, 가장 최근 값)
        
        # 년도별 데이터 리스트
        self.yearly_data: list[YearlyFinancialData] = []
        
        # === 필터 결과 ===
        self.passed_all_filters: bool = True  # 전체 필터 통과 여부
        self.filter_operating_income: bool = True  # 영업이익 필터 통과 여부
        self.filter_net_income: bool = True  # 당기순이익 필터 통과 여부
        self.filter_revenue_cagr: bool = True  # 매출액 CAGR 필터 통과 여부
        self.filter_total_assets_operating_income_ratio: bool = True  # 총자산영업이익률 필터 통과 여부
