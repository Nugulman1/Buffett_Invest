"""
데이터 수집 오케스트레이터
"""
import logging

from django.conf import settings

from apps.service.dart import DartDataService
from apps.service.ecos import EcosDataService
from apps.service.calculator import IndicatorCalculator
from apps.service.filter import CompanyFilter
from apps.service.dart_extractor import extract_financial_indicators_from_dart
from apps.models import CompanyFinancialObject, YearlyFinancialDataObject
from apps.dart.client import DartClient
from apps.service.db import save_company_to_db, db_write_lock, update_second_filter_result

logger = logging.getLogger(__name__)

# DART 다중회사 주요재무지표 ROE 지표코드
ROE_IDX_CODE = 'M211550'

# 판관비율: fnlttCmpnyIndx 수익성지표 응답에서 idx_nm이 '판관비율' 또는 '판매비와관리비율'인 항목으로 매칭
PANGWAN_NAMES = ('판관비율', '판매비와관리비율')


class DataOrchestrator:
    """DART와 ECOS 데이터 수집을 조율하는 오케스트레이터"""
    
    def __init__(self):
        self.dart_service = DartDataService()
        self.ecos_service = EcosDataService()
        self.dart_client = DartClient()

    @staticmethod
    def _fill_roe_from_indicators(company_data: CompanyFinancialObject) -> None:
        """yearly_indicators의 M211550(ROE) 값을 yearly_data.roe에 채움. 없으면 당기순이익/자본총계로 계산(폴백)."""
        indicators = getattr(company_data, 'yearly_indicators', None) or {}
        corp_code = getattr(company_data, 'corp_code', '')
        for yearly_data in company_data.yearly_data:
            year_indicators = indicators.get(yearly_data.year, {})
            val = year_indicators.get(ROE_IDX_CODE)
            yearly_data.roe = float(val) if val is not None else None
            # 폴백: DART ROE 없으면 당기순이익/자본총계로 수동 계산
            if yearly_data.roe is None and yearly_data.net_income is not None and yearly_data.total_equity is not None and yearly_data.total_equity > 0:
                yearly_data.roe = yearly_data.net_income / yearly_data.total_equity

    @staticmethod
    def _fill_selling_admin_expense_ratio_from_indicators(company_data: CompanyFinancialObject) -> None:
        """yearly_indicators에서 판관비율(지표명 매칭) 값을 yearly_data.selling_admin_expense_ratio에 채움."""
        indicators = getattr(company_data, 'yearly_indicators', None) or {}
        names = getattr(company_data, 'yearly_indicator_names', None) or {}
        for yearly_data in company_data.yearly_data:
            year = yearly_data.year
            year_indicators = indicators.get(year, {})
            year_names = names.get(year, {})
            value = None
            for idx_code, idx_nm in (year_names or {}).items():
                if idx_nm and any(p in idx_nm for p in PANGWAN_NAMES):
                    val = year_indicators.get(idx_code)
                    if val is not None:
                        try:
                            value = float(val)
                            if value > 1:
                                value = value / 100.0
                        except (TypeError, ValueError):
                            pass
                    break
            yearly_data.selling_admin_expense_ratio = value

    def _fill_advanced_indicators(self, company_data: CompanyFinancialObject,
                                  bond_yield_decimal: float, market_cap: int | None = None) -> None:
        """
        DART 전체재무제표(fnlttSinglAcntAll) 1콜로 최근 3개년 ROIC/WACC/FCF/IC 자동 계산 (T3).

        company_data.yearly_data 객체에 in-place 기록 → 이후 save_company_to_db가 영속화.
        - 이자부채·이자비용·CFO·CAPEX·현금·비지배지분을 LLM 없이 DART 계정에서 추출(dart_extractor).
        - equity는 total_equity로 세팅(T8와 동일 패턴).
        - 미계산 연도(데이터 없음/추출 없음)는 roic/wacc/fcf=None → 2차 필터에서 제외.
        - EV는 market_cap이 있을 때만 계산(없으면 None, EV/IC는 현재 필터 미사용).
        - bond_yield_decimal(소수)을 calculator의 퍼센트 입력으로 변환.
        """
        corp_code = company_data.corp_code
        if not company_data.yearly_data:
            return
        bsns_year = company_data.latest_annual_report_year or max(
            (yd.year for yd in company_data.yearly_data), default=None
        )
        if not bsns_year:
            return
        try:
            rows = self.dart_client.get_financial_statement_all(corp_code, str(bsns_year))
            if not rows:
                # CFS(연결)를 안 내는 중소형사(별도만 제출)는 OFS로 폴백.
                # 미폴백 시 cash·이자부채·CFO 미추출 → ROIC/WACC/FCF 전부 None.
                rows = self.dart_client.get_financial_statement_all(
                    corp_code, str(bsns_year), fs_div='OFS'
                )
        except Exception as e:
            logger.warning("전체재무제표 조회 실패 %s: %s", corp_code, e)
            rows = []
        extracted = extract_financial_indicators_from_dart(rows, int(bsns_year)) if rows else {}

        tax_rate = settings.CALCULATOR_DEFAULTS['TAX_RATE'] / 100.0
        erp = settings.CALCULATOR_DEFAULTS['EQUITY_RISK_PREMIUM']
        bond_yield_pct = (bond_yield_decimal or 0.0) * 100.0  # 소수→퍼센트

        for yd in company_data.yearly_data:
            row = extracted.get(yd.year)
            if not row or yd.operating_income is None or yd.total_equity is None:
                yd.roic = None
                yd.wacc = None
                yd.fcf = None
                continue
            # equity는 total_equity 기반 property(T8) — 별도 세팅 불필요
            yd.cfo = row["cfo"]
            yd.tangible_asset_acquisition = row["tangible_asset_acquisition"]
            yd.intangible_asset_acquisition = row["intangible_asset_acquisition"]
            yd.cash_and_cash_equivalents = row["cash_and_cash_equivalents"]
            yd.interest_bearing_debt = row["interest_bearing_debt"]
            yd.interest_expense = row["interest_expense"]
            yd.noncontrolling_interest = row["noncontrolling_interest"]
            yd.dividend_paid = row["dividend_paid"] or None
            yd.fcf = IndicatorCalculator.calculate_fcf(yd)
            # 이자부채 0 = 미포착 의심: 차입금을 '금융부채' 등으로 뭉뚱그려 못 잡았거나(셀트리온형)
            # 진짜 무차입. 0을 유효값으로 WACC/ROIC를 계산하면 과소 왜곡되므로, 이자부채 의존
            # 지표(WACC/ROIC/IC/EV)는 계산하지 않고 로그로 분리한다(누적 로그로 패턴 추적).
            if not yd.interest_bearing_debt:
                yd.roic = None
                yd.wacc = None
                yd.invested_capital = None
                yd.ev = None
                logger.warning(
                    "[이자부채0] 미포착 의심 → WACC/ROIC/IC/EV 제외 (%s %s, %s년)",
                    company_data.company_name or "", corp_code, yd.year,
                )
            else:
                yd.roic = IndicatorCalculator.calculate_roic(yd, tax_rate)
                yd.wacc = IndicatorCalculator.calculate_wacc(yd, bond_yield_pct, tax_rate, erp)
                yd.invested_capital, ev = IndicatorCalculator.compute_ic_ev(yd, market_cap)
                if ev is not None:
                    yd.ev = ev
            if yd.fcf and yd.fcf > 0 and yd.dividend_paid:
                yd.dividend_payout_ratio = yd.dividend_paid / yd.fcf

    def _ensure_bond_yield(self) -> float:
        """
        5년 국채수익률을 하루 단위로 캐싱(BondYield 단일 레코드 id=1)하고 소수값 반환.

        단건/배치 공통(T12). DB 접근은 db_write_lock으로 직렬화해 SQLite
        'database is locked' 방지. ECOS는 백분율 반환이라 /100으로 소수화.
        실패해도 0.0 반환(계속 진행).
        """
        from django.utils import timezone
        from datetime import timedelta
        from django.apps import apps as django_apps

        BondYieldModel = django_apps.get_model('apps', 'BondYield')
        try:
            with db_write_lock:
                bond_yield_obj, _ = BondYieldModel.objects.get_or_create(
                    id=1,
                    defaults={
                        'yield_value': 0.0,
                        'collected_at': timezone.now() - timedelta(days=2),  # 기본값: 2일 전
                    },
                )
                if timezone.now() - bond_yield_obj.collected_at > timedelta(days=1):
                    bond_yield = self.ecos_service.collect_bond_yield_5y()
                    bond_yield_obj.yield_value = bond_yield / 100.0 if bond_yield else 0.0
                    bond_yield_obj.collected_at = timezone.now()
                    bond_yield_obj.save()
                return bond_yield_obj.yield_value or 0.0
        except Exception as e:
            logger.warning("채권수익률 수집 실패: %s", e)
            return 0.0

    def _finalize_company(self, company_data: CompanyFinancialObject, corp_code: str,
                          bond_yield_decimal: float, *, save_to_db: bool = True,
                          raise_on_save_error: bool = False) -> None:
        """
        회사 1건의 마무리: 회사명 → ROE/판관비 → 기본비율 → 고급지표(ROIC/WACC/FCF/IC)
        → 필터 → (선택)저장+2차필터. 단건/배치 공통(T12).

        save 실패 처리는 호출자별로 다름:
        - 단건: raise_on_save_error=False → 로그만 남기고 데이터는 그대로 반환.
        - 배치: raise_on_save_error=True → 예외 전파해 해당 회사를 'failed'로 마킹.
        """
        try:
            company_info = self.dart_client.get_company_info(corp_code)
            if company_info:
                company_data.company_name = company_info.get('corp_name', '')
        except Exception as e:
            logger.warning("기업 정보 조회 실패 %s: %s", corp_code, e)

        self._fill_roe_from_indicators(company_data)
        self._fill_selling_admin_expense_ratio_from_indicators(company_data)
        IndicatorCalculator.calculate_basic_financial_ratios(company_data)

        # ROIC/WACC/FCF/IC 자동 계산 (DART 전체재무제표) → 2차 필터 자동화
        try:
            self._fill_advanced_indicators(company_data, bond_yield_decimal)
        except Exception as e:
            logger.warning("고급지표 계산 실패 %s: %s", corp_code, e)

        try:
            CompanyFilter.apply_all_filters(company_data)
        except Exception as e:
            logger.warning("필터 적용 실패 %s: %s", corp_code, e)

        if save_to_db:
            try:
                save_company_to_db(company_data)
                update_second_filter_result(corp_code)  # ROIC/WACC 저장 후 2차 필터 갱신
            except Exception as e:
                logger.warning("DB 저장 실패 %s: %s", corp_code, e)
                if raise_on_save_error:
                    raise

    def collect_company_data(self, corp_code: str, save_to_db: bool = True) -> CompanyFinancialObject:
        """
        회사 데이터 수집 (DART + ECOS)
        
        Args:
            corp_code: 고유번호 (8자리)
            save_to_db: DB 저장 여부 (기본값: True, 병렬 처리 시 False로 설정)
        
        Returns:
            CompanyFinancialObject
        """
        # CompanyFinancialObject 생성
        company_data = CompanyFinancialObject()
        company_data.corp_code = corp_code

        # 최근 5년 연도 리스트 생성
        years = self.dart_service._get_recent_years(5)

        # DART 기본 지표 수집 (다중 API 사용, 단일은 list 1개로 호출)
        company_data_map = self.dart_service.fill_basic_indicators_multi([corp_code], years)
        multi_data = company_data_map.get(corp_code)
        if multi_data:
            company_data.yearly_data = multi_data.yearly_data
            company_data.latest_annual_rcept_no = multi_data.latest_annual_rcept_no
            company_data.latest_annual_report_year = multi_data.latest_annual_report_year
        # DART 주요재무지표 수집 (ROE M211550 등) → yearly_data.roe 채움
        indicators_map, indicator_names_map = self.dart_service.fill_financial_indicators_multi([corp_code], years)
        company_data.yearly_indicators = indicators_map.get(corp_code, {})
        company_data.yearly_indicator_names = indicator_names_map.get(corp_code, {})

        # 채권수익률 캐싱 + 회사 마무리(계산·필터·저장)는 단건/배치 공통 헬퍼로(T12)
        bond_yield_decimal = self._ensure_bond_yield()
        self._finalize_company(company_data, corp_code, bond_yield_decimal,
                               save_to_db=save_to_db, raise_on_save_error=False)
        return company_data

    def collect_companies_data_batch(self, corp_codes: list[str]) -> list[dict]:
        """
        다중회사 주요계정 API로 배치 수집 후 회사별 계산·필터·저장.
        회사 단위로 try/except 하여 일부 실패해도 성공한 건은 저장.

        Args:
            corp_codes: 고유번호 리스트 (최대 100개)

        Returns:
            [{"corp_code": ..., "status": "success"|"failed", "passed_all_filters": bool, "error": ...}, ...]
        """
        if not corp_codes:
            return []
        years = self.dart_service._get_recent_years(5)
        company_data_map = self.dart_service.fill_basic_indicators_multi(corp_codes, years)
        indicators_map, indicator_names_map = self.dart_service.fill_financial_indicators_multi(corp_codes, years)
        for corp_code in corp_codes:
            company_data = company_data_map.get(corp_code)
            if company_data is not None:
                company_data.yearly_indicators = indicators_map.get(corp_code, {})
                company_data.yearly_indicator_names = indicator_names_map.get(corp_code, {})

        # 채권수익률 1회 조회/캐시 (단건/배치 공통 헬퍼, DB 접근은 락으로 직렬화)
        bond_yield_decimal = self._ensure_bond_yield()

        results = []
        for corp_code in corp_codes:
            company_data = company_data_map.get(corp_code)
            if not company_data:
                results.append({
                    'corp_code': corp_code,
                    'status': 'failed',
                    'passed_all_filters': False,
                    'error': '수집된 연간 데이터 없음',
                })
                continue
            try:
                # 배치는 저장 실패 시 해당 회사를 'failed'로 마킹해야 하므로 예외 전파
                self._finalize_company(company_data, corp_code, bond_yield_decimal,
                                       save_to_db=True, raise_on_save_error=True)
                results.append({
                    'corp_code': corp_code,
                    'status': 'success',
                    'passed_all_filters': company_data.passed_all_filters,
                    'company_name': company_data.company_name or '',
                    'error': None,
                })
            except Exception as e:
                logger.warning("배치 내 회사 저장 실패 %s: %s", corp_code, e)
                results.append({
                    'corp_code': corp_code,
                    'status': 'failed',
                    'passed_all_filters': False,
                    'error': str(e),
                })
        return results


