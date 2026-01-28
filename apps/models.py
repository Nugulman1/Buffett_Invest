"""
재무제표 데이터 모델
"""
from django.db import models

# Django ORM 모델 (Python 클래스보다 먼저 정의)
class Company(models.Model):
    """회사 정보 및 필터 결과를 저장하는 Django 모델"""
    corp_code = models.CharField(max_length=8, primary_key=True, verbose_name='고유번호')
    company_name = models.CharField(max_length=200, blank=True, verbose_name='회사명')
    last_collected_at = models.DateTimeField(null=True, blank=True, verbose_name='마지막수집일시')
    passed_all_filters = models.BooleanField(default=False, verbose_name='전체필터통과')
    filter_operating_income = models.BooleanField(default=False, verbose_name='영업이익필터')
    filter_net_income = models.BooleanField(default=False, verbose_name='당기순이익필터')
    filter_revenue_cagr = models.BooleanField(default=False, verbose_name='매출액CAGR필터')
    filter_operating_margin = models.BooleanField(default=False, verbose_name='영업이익률필터')
    filter_roe = models.BooleanField(default=False, verbose_name='ROE필터')
    memo = models.TextField(blank=True, null=True, verbose_name='메모')
    memo_updated_at = models.DateTimeField(null=True, blank=True, verbose_name='메모수정일시')
    latest_annual_rcept_no = models.CharField(max_length=14, blank=True, null=True, verbose_name='최근사업보고서접수번호')
    latest_annual_report_year = models.IntegerField(null=True, blank=True, verbose_name='최근사업보고서연도')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일시')
    
    class Meta:
        db_table = 'company'
        verbose_name = '회사'
        verbose_name_plural = '회사들'
        indexes = [
            models.Index(fields=['corp_code']),
            models.Index(fields=['company_name']),  # 기업명 검색 성능 향상
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
    operating_margin = models.FloatField(default=0.0, verbose_name='영업이익률')  # 계산 방식 (영업이익/매출액)
    roe = models.FloatField(default=0.0, verbose_name='ROE')  # 계산 방식 (당기순이익/자본총계)
    interest_bearing_debt = models.BigIntegerField(default=0, null=True, blank=True, verbose_name='이자부채')
    fcf = models.BigIntegerField(default=0, null=True, blank=True, verbose_name='자유현금흐름')
    roic = models.FloatField(default=0.0, null=True, blank=True, verbose_name='투하자본수익률')
    wacc = models.FloatField(default=0.0, null=True, blank=True, verbose_name='가중평균자본비용')
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


class QuarterlyFinancialData(models.Model):
    """분기별 재무 데이터를 저장하는 Django 모델"""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='quarterly_data', verbose_name='회사')
    year = models.IntegerField(verbose_name='사업연도')
    quarter = models.IntegerField(verbose_name='분기')  # 1: 1분기, 2: 반기, 3: 3분기
    reprt_code = models.CharField(max_length=10, verbose_name='보고서코드')  # 11013: 1분기, 11012: 반기, 11014: 3분기
    rcept_no = models.CharField(max_length=14, blank=True, verbose_name='접수번호')
    revenue = models.BigIntegerField(default=0, verbose_name='매출액')
    operating_income = models.BigIntegerField(default=0, verbose_name='영업이익')
    net_income = models.BigIntegerField(default=0, verbose_name='당기순이익')
    total_assets = models.BigIntegerField(default=0, verbose_name='자산총계')
    total_equity = models.BigIntegerField(default=0, verbose_name='자본총계')
    operating_margin = models.FloatField(default=0.0, verbose_name='영업이익률')  # 계산 방식 (영업이익/매출액)
    roe = models.FloatField(default=0.0, verbose_name='ROE')  # 계산 방식 (당기순이익/자본총계)
    collected_at = models.DateTimeField(auto_now_add=True, verbose_name='수집일시')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일시')
    
    class Meta:
        db_table = 'quarterly_financial_data'
        verbose_name = '분기별재무데이터'
        verbose_name_plural = '분기별재무데이터들'
        unique_together = [['company', 'year', 'quarter']]
        indexes = [
            models.Index(fields=['company', 'year', 'quarter']),
            models.Index(fields=['year', 'quarter']),
        ]
    
    def __str__(self):
        quarter_names = {1: '1분기', 2: '반기', 3: '3분기'}
        quarter_name = quarter_names.get(self.quarter, f'{self.quarter}분기')
        return f"{self.company.company_name} - {self.year}년 {quarter_name}"


class FavoriteGroup(models.Model):
    """즐겨찾기 그룹 모델"""
    name = models.CharField(max_length=100, verbose_name='그룹명')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성일시')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정일시')
    
    class Meta:
        db_table = 'favorite_group'
        verbose_name = '즐겨찾기그룹'
        verbose_name_plural = '즐겨찾기그룹들'
        indexes = [
            models.Index(fields=['name']),
        ]
    
    def __str__(self):
        return self.name


class Favorite(models.Model):
    """즐겨찾기 모델"""
    group = models.ForeignKey(FavoriteGroup, on_delete=models.CASCADE, related_name='favorites', verbose_name='그룹')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='favorites', verbose_name='회사')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='추가일시')
    
    class Meta:
        db_table = 'favorite'
        verbose_name = '즐겨찾기'
        verbose_name_plural = '즐겨찾기들'
        unique_together = [['group', 'company']]
        indexes = [
            models.Index(fields=['group', 'company']),
            models.Index(fields=['company']),
        ]
    
    def __str__(self):
        return f"{self.group.name} - {self.company.company_name}"


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
        self.rcept_no = ''
        if raw_data and len(raw_data) > 0:
            self.rcept_no = (raw_data[0].get('rcept_no') or '').strip()
        
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
    
    def __init__(self, year: int):
        """
        Args:
            year: 사업연도
        """
        # 회사 정보
        self.year: int = year
        
        # === 기본 지표 (DART API) ===
        self.revenue: int = 0  # 매출액 (5Y)
        self.operating_income: int = 0  # 영업이익 (5Y)
        self.net_income: int = 0  # 당기순이익 (5Y)
        self.total_assets: int = 0  # 자산총계
        self.total_equity: int = 0  # 자본총계
        self.operating_margin: float = 0.0  # 영업이익률 (%) - 계산 방식 (영업이익/매출액)
        self.roe: float = 0.0  # ROE (%) - 계산 방식 (당기순이익/자본총계)
        
        # === 계산에 사용하는 기본 지표 ===
        self.tangible_asset_acquisition: int = 0  # 유형자산 취득
        self.intangible_asset_acquisition: int = 0  # 무형자산 취득
        self.cfo: int = 0  # 영업활동현금흐름
        self.equity: int = 0  # 자기자본
        self.cash_and_cash_equivalents: int = 0  # 현금및현금성자산
        self.interest_bearing_debt: int = 0  # 이자부채 (통합)
        self.interest_expense: int = 0  # 이자비용 (WACC 계산에 사용)
        self.beta: float = 1.0  # 베타 (고정)
        self.mrp: float = 5.0  # MRP (고정)
        
        # 계산된 지표
        self.fcf: int = 0  # 자유현금흐름
        self.icr: float = 0.0  # 이자보상비율 (ratio)
        self.roic: float = 0.0  # 투하자본수익률 (%)
        self.wacc: float = 0.0  # 가중평균자본비용 (%)

        # 사업보고서 접수번호 (fnlttSinglAcnt raw_data 기준, DB 미저장)
        # fill_basic_indicators 정렬 후 가장 최근 연도 것만 Company에 저장
        self.rcept_no: str | None = None

class CompanyFinancialObject:
    """회사 재무제표 데이터 객체"""
    
    def __init__(self):
        # 회사 정보
        self.company_name: str = ""
        self.corp_code: str = ""
        
        # 년도별 데이터 리스트
        self.yearly_data: list[YearlyFinancialDataObject] = []
        
        # 최근 사업보고서 링크용 (5년 수집 정렬 직후 채움)
        self.latest_annual_rcept_no: str | None = None
        self.latest_annual_report_year: int | None = None
        
        # === 필터 결과 ===
        self.passed_all_filters: bool = False  # 전체 필터 통과 여부
        self.filter_operating_income: bool = False  # 영업이익 필터 통과 여부
        self.filter_net_income: bool = False  # 당기순이익 필터 통과 여부
        self.filter_revenue_cagr: bool = False  # 매출액 CAGR 필터 통과 여부
        self.filter_operating_margin: bool = False  # 영업이익률 필터 통과 여부
        self.filter_roe: bool = False  # ROE 필터 통과 여부
