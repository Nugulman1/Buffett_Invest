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
        self.year = year
        self.reprt_code = reprt_code
        self.fs_div = fs_div
        
        # O(1) 조회를 위한 인덱싱 (계정명을 키로, 값만 저장)
        self.account_index = {}
        for item in raw_data:
            account_nm = item.get('account_nm', '')
            if account_nm:
                # 이미 같은 계정명이 있으면 덮어쓰지 않음 (CFS 우선)
                if account_nm not in self.account_index:
                    self.account_index[account_nm] = {
                        'thstrm_amount': item.get('thstrm_amount', '0'),
                        'frmtrm_amount': item.get('frmtrm_amount', '0'),
                        'bfefrmtrm_amount': item.get('bfefrmtrm_amount', '0'),
                    }
    
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
        
        # 기본 지표 (계산용)
        self.total_assets: int = 0  # 자산총계
        self.operating_income: int = 0  # 영업이익
        self.net_income: int = 0  # 당기순이익
        self.current_liabilities: int = 0  # 유동부채
        self.interest_bearing_current_liabilities: int = 0  # 이자부유동부채
        self.tangible_asset_acquisition: int = 0  # 유형자산 취득
        self.intangible_asset_acquisition: int = 0  # 무형자산 취득
        self.cfo: int = 0  # 영업활동현금흐름
        self.interest_expense: int = 0  # 이자비용
        self.equity: int = 0  # 자기자본
        self.cash_and_cash_equivalents: int = 0  # 현금및현금성자산
        self.short_term_borrowings: int = 0  # 단기차입금
        self.current_portion_of_long_term_borrowings: int = 0  # 유동성장기차입금
        self.long_term_borrowings: int = 0  # 장기차입금
        self.bonds: int = 0  # 사채
        self.lease_liabilities: int = 0  # 리스부채
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
