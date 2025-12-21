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
                # 계정값만 저장 (원본 데이터는 저장하지 않음)
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


class CompanyFinancialObject:
    """회사 재무제표 데이터 객체"""
    
    def __init__(self):
        # 회사 정보
        self.company_name: str = ""
        self.business_type_code: str = ""
        self.business_type_name: str = ""
        self.corp_code: str = ""
        self.collection_year: int = 0
        
        # 재무 지표
        self.FCF: int = 0
        self.CFO: int = 0
        self.Net_Income: int = 0
        
        # 비율 지표
        self.ICR: float = 0.0  # 이자보상비율 (ratio)
        self.ROIC: float = 0.0  # 투하자본수익률 (%)
        self.WACC: float = 0.0  # 가중평균자본비용 (%)
