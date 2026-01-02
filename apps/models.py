"""
재무제표 데이터 모델
"""
from django.db import models

# Django ORM 모델 (Python 클래스보다 먼저 정의)
class Company(models.Model):
    """회사 정보 및 필터 결과를 저장하는 Django 모델"""
    corp_code = models.CharField(max_length=8, primary_key=True, verbose_name='고유번호')
    company_name = models.CharField(max_length=200, blank=True, verbose_name='회사명')
    business_type_code = models.CharField(max_length=10, blank=True, verbose_name='업종코드')
    business_type_name = models.CharField(max_length=50, blank=True, verbose_name='업종명')
    bond_yield_5y = models.FloatField(default=0.0, verbose_name='채권수익률(5년)')
    last_collected_at = models.DateTimeField(null=True, blank=True, verbose_name='마지막수집일시')
    passed_all_filters = models.BooleanField(default=False, verbose_name='전체필터통과')
    filter_operating_income = models.BooleanField(default=False, verbose_name='영업이익필터')
    filter_net_income = models.BooleanField(default=False, verbose_name='당기순이익필터')
    filter_revenue_cagr = models.BooleanField(default=False, verbose_name='매출액CAGR필터')
    filter_total_assets_operating_income_ratio = models.BooleanField(default=False, verbose_name='총자산영업이익률필터')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일시')
    
    class Meta:
        db_table = 'company'
        verbose_name = '회사'
        verbose_name_plural = '회사들'
        indexes = [
            models.Index(fields=['corp_code']),
        ]
    
    def __str__(self):
        return f"{self.company_name} ({self.corp_code})"


class BondYield(models.Model):
    """채권수익률 모델 (단일 레코드만 유지)"""
    yield_value = models.FloatField(default=0.0, verbose_name='채권수익률(5년)')
    collected_at = models.DateTimeField(verbose_name='수집일시')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일시')
    
    class Meta:
        db_table = 'bond_yield'
        verbose_name = '채권수익률'
        verbose_name_plural = '채권수익률'
    
    def __str__(self):
        return f"채권수익률: {self.yield_value:.4f}% (수집일: {self.collected_at})"


class ApiCallStats(models.Model):
    """일별 API 호출 통계 모델"""
    date = models.DateField(unique=True, verbose_name='날짜')
    dart_calls = models.IntegerField(default=0, verbose_name='DART API 호출 횟수')
    ecos_calls = models.IntegerField(default=0, verbose_name='ECOS API 호출 횟수')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일시')
    
    class Meta:
        db_table = 'api_call_stats'
        verbose_name = 'API 호출 통계'
        verbose_name_plural = 'API 호출 통계들'
        indexes = [
            models.Index(fields=['date']),
        ]
    
    def __str__(self):
        return f"{self.date} - DART: {self.dart_calls}회, ECOS: {self.ecos_calls}회"


class YearlyFinancialData(models.Model):
    """년도별 재무 데이터를 저장하는 Django 모델"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='yearly_data', verbose_name='회사')
    year = models.IntegerField(verbose_name='사업연도')
    revenue = models.BigIntegerField(default=0, verbose_name='매출액')
    operating_income = models.BigIntegerField(default=0, verbose_name='영업이익')
    net_income = models.BigIntegerField(default=0, verbose_name='당기순이익')
    total_assets = models.BigIntegerField(default=0, verbose_name='자산총계')
    total_equity = models.BigIntegerField(default=0, verbose_name='자본총계')
    # 주의: 아래 두 필드는 현재 수집하지 않음 (기본 지표 API에 해당 계정이 없음)
    # API 호출 최적화를 위해 재무지표 API 호출을 제거했으며, 매출총이익률과 판관비율은 수집하지 않음
    gross_profit_margin = models.FloatField(default=0.0, verbose_name='매출총이익률')  # 사용 안 함 (API 호출 제거)
    selling_admin_expense_ratio = models.FloatField(default=0.0, verbose_name='판관비율')  # 사용 안 함 (API 호출 제거)
    total_assets_operating_income_ratio = models.FloatField(default=0.0, verbose_name='총자산영업이익률')  # 계산 방식 (영업이익/자산총계)
    roe = models.FloatField(default=0.0, verbose_name='ROE')  # 계산 방식 (당기순이익/자본총계)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일시')
    
    class Meta:
        db_table = 'yearly_financial_data'
        verbose_name = '년도별재무데이터'
        verbose_name_plural = '년도별재무데이터들'
        unique_together = [['company', 'year']]
        indexes = [
            models.Index(fields=['company', 'year']),
            models.Index(fields=['year']),
        ]
    
    def __str__(self):
        return f"{self.company.company_name} - {self.year}년"


# 기존 Python 클래스들 (하위 호환성 유지)


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


class YearlyFinancialDataObject:
    """년도별 재무 데이터 객체 (Python 클래스)"""
    
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
        # 주의: 아래 두 필드는 현재 수집하지 않음 (기본 지표 API에 해당 계정이 없음)
        # API 호출 최적화를 위해 재무지표 API 호출을 제거했으며, 매출총이익률과 판관비율은 수집하지 않음
        self.gross_profit_margin: float = 0.0  # 매출총이익률 (%) - 사용 안 함 (API 호출 제거)
        self.selling_admin_expense_ratio: float = 0.0  # 판관비율 (%) - 사용 안 함 (API 호출 제거)
        self.total_assets_operating_income_ratio: float = 0.0  # 총자산영업이익률 (%) - 계산 방식 (영업이익/자산총계)
        self.roe: float = 0.0  # ROE (%) - 계산 방식 (당기순이익/자본총계)
        
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
        self.yearly_data: list[YearlyFinancialDataObject] = []
        
        # === 필터 결과 ===
        self.passed_all_filters: bool = True  # 전체 필터 통과 여부
        self.filter_operating_income: bool = True  # 영업이익 필터 통과 여부
        self.filter_net_income: bool = True  # 당기순이익 필터 통과 여부
        self.filter_revenue_cagr: bool = True  # 매출액 CAGR 필터 통과 여부
        self.filter_total_assets_operating_income_ratio: bool = True  # 총자산영업이익률 필터 통과 여부
