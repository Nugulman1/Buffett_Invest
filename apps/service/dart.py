"""
DART 데이터 수집 서비스
"""
import json
import logging
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from apps.dart.client import DartClient
from apps.models import FinancialStatementData, YearlyFinancialDataObject, CompanyFinancialObject
from apps.utils import normalize_account_name

logger = logging.getLogger(__name__)


class DartDataService:
    """DART API를 통한 재무제표 데이터 수집"""
    
    # 매핑 파일 캐시 (클래스 변수)
    _indicator_mappings_cache = None
    
    def __init__(self):
        self.client = DartClient()
    
    def _get_recent_years(self, count=5):
        """
        최근 N년 연도 리스트 반환
        연간보고서는 다음 해에 발행되므로:
        - 현재 월이 4월 이상이면: (현재연도-5) ~ (현재연도-1)
        - 현재 월이 1~3월이면: (현재연도-6) ~ (현재연도-2)
        
        Args:
            count: 수집할 연도 수 (기본값: 5)
            
        Returns:
            연도 리스트 (예: [2020, 2021, 2022, 2023, 2024])
        """
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        if current_month >= 4:
            # 4월 이후: 올해 연도까지 포함 가능
            start_year = current_year - count
            end_year = current_year - 1
        else:
            # 1~3월: 작년 연도까지만 포함 가능
            start_year = current_year - count - 1
            end_year = current_year - 2
        
        return list(range(start_year, end_year + 1))  # end_year 포함

    def _load_indicator_mappings(self):
        """
        매핑표 로드 (캐싱 적용)
        
        Returns:
            매핑 테이블 딕셔너리
        """
        # 캐시가 있으면 반환
        if DartDataService._indicator_mappings_cache is not None:
            return DartDataService._indicator_mappings_cache
        
        # 캐시가 없으면 파일에서 로드
        mappings_path = Path(__file__).parent.parent.parent / 'indicators_mappings.json'
        with open(mappings_path, 'r', encoding='utf-8') as f:
            mappings = json.load(f)
            # 클래스 변수에 캐싱
            DartDataService._indicator_mappings_cache = mappings
            return mappings
    
    def fill_basic_indicators_multi(
        self, corp_codes: list[str], years: list[int]
    ) -> dict[str, CompanyFinancialObject]:
        """
        다중회사 주요계정 API로 100개 회사 x 연도별 데이터 수집 후 회사별 CompanyFinancialObject 반환.

        배치 내 일부 연도 실패 시 해당 연도만 로그 후 스킵. 회사별로 yearly_data 병합 후 반환.
        """
        if not corp_codes:
            return {}
        # 종목코드→corp_code 매핑이 없으면 API 응답의 stock_code를 corp_code로 연결할 수 없음. 진입 경로(예: API 단건 조회)에선 load가 호출되지 않을 수 있으므로 여기서 보장.
        if not self.client._corp_code_mapping_cache:
            self.client.load_corp_code_xml()
        corp_set = set(corp_codes)
        # stock_code -> corp_code (요청 corp_set에 해당하는 것만). 종목코드는 6자리로 통일(API가 앞자리 0 생략할 수 있음)
        def _norm_stock(s):
            return str(s).strip().zfill(6) if s else ""
        stock_to_corp = {
            _norm_stock(k): v for k, v in self.client._corp_code_mapping_cache.items() if v in corp_set
        }
        mappings = self._load_indicator_mappings()
        reverse_mapping: dict[str, str] = {}
        for mapping_config in mappings.values():
            internal_field = mapping_config.get('internal_field')
            if not internal_field:
                continue
            for variant in mapping_config.get('dart_variants', []):
                normalized_variant = normalize_account_name(variant)
                reverse_mapping.setdefault(normalized_variant, internal_field)

        year_amount_pairs = [
            (0, 'thstrm_amount'),
            (-1, 'frmtrm_amount'),
            (-2, 'bfefrmtrm_amount'),
        ]

        # corp_code -> year -> YearlyFinancialDataObject
        corp_year_to_data: dict[str, dict[int, YearlyFinancialDataObject]] = defaultdict(dict)
        latest_rcept: dict[str, tuple[str | None, int | None]] = {}  # corp_code -> (rcept_no, year)

        for year in years:
            year_str = str(year)
            try:
                raw_list = self.client.get_financial_statement_multi(
                    corp_codes, year_str, reprt_code='11011'
                )
            except Exception as e:
                logger.warning(
                    "다중회사 주요계정 API 실패 (배치 %s건, 연도 %s): %s",
                    len(corp_codes), year_str, e,
                )
                continue
            if not raw_list:
                continue

            # 행별 stock_code, fs_div. CFS 우선, 없으면 OFS 사용 (일부 회사는 연결재무제표 미제출)
            by_stock_cfs: dict[str, list] = defaultdict(list)
            by_stock_ofs: dict[str, list] = defaultdict(list)
            for row in raw_list:
                fs_div = (row.get('fs_div') or '').strip()
                raw_sc = row.get('stock_code')
                stock_code = _norm_stock(raw_sc) if raw_sc is not None and raw_sc != '' else ''
                if not stock_code:
                    continue
                if fs_div == 'OFS':
                    by_stock_ofs[stock_code].append(row)
                else:
                    by_stock_cfs[stock_code].append(row)
            by_stock = {}
            fs_div_used: dict[str, str] = {}
            for sc in set(by_stock_cfs.keys()) | set(by_stock_ofs.keys()):
                if by_stock_cfs[sc]:
                    by_stock[sc] = by_stock_cfs[sc]
                    fs_div_used[sc] = 'CFS'
                else:
                    by_stock[sc] = by_stock_ofs[sc]
                    fs_div_used[sc] = 'OFS'

            for stock_code, rows in by_stock.items():
                corp_code = stock_to_corp.get(stock_code)
                if not corp_code:
                    continue
                fs_div_choice = fs_div_used.get(stock_code, 'CFS')
                fs_data = FinancialStatementData(
                    year=year_str, reprt_code='11011', fs_div=fs_div_choice, raw_data=rows
                )
                rcept_no = (fs_data.rcept_no or '').strip() or None
                for offset, amount_type in year_amount_pairs:
                    target_year = year + offset
                    if target_year not in years:
                        continue
                    if corp_code not in corp_year_to_data:
                        corp_year_to_data[corp_code] = {}
                    if target_year in corp_year_to_data[corp_code]:
                        continue
                    yearly_data = YearlyFinancialDataObject(year=target_year)
                    yearly_data.rcept_no = rcept_no
                    for norm_name, account_data in fs_data.normalized_account_index.items():
                        internal_field = reverse_mapping.get(norm_name)
                        if not internal_field or not hasattr(yearly_data, internal_field):
                            continue
                        amount = account_data.get(amount_type, '0')
                        try:
                            value = int(amount.replace(',', '')) if amount else None
                        except (ValueError, AttributeError):
                            value = None
                        setattr(yearly_data, internal_field, value)
                    corp_year_to_data[corp_code][target_year] = yearly_data
                    if target_year == year and rcept_no:
                        if corp_code not in latest_rcept or year > latest_rcept[corp_code][1]:
                            latest_rcept[corp_code] = (rcept_no, year)

        result: dict[str, CompanyFinancialObject] = {}
        for corp_code, year_to_data in corp_year_to_data.items():
            if not year_to_data:
                continue
            company_data = CompanyFinancialObject()
            company_data.corp_code = corp_code
            sorted_items = sorted(year_to_data.items(), key=lambda x: x[0])
            for _, yearly_data in sorted_items:
                company_data.yearly_data.append(yearly_data)
            rcept_no, report_year = latest_rcept.get(corp_code, (None, None))
            company_data.latest_annual_rcept_no = rcept_no
            company_data.latest_annual_report_year = report_year
            result[corp_code] = company_data
        return result

    def fill_financial_indicators_multi(
        self,
        corp_codes: list[str],
        years: list[int],
        idx_cl_codes: list[str] | None = None,
    ) -> tuple[dict[str, dict[int, dict[str, float]]], dict[str, dict[int, dict[str, str]]]]:
        """
        다중회사 주요재무지표 API로 연도·지표분류별 수집 후 (값 맵, 지표명 맵) 반환.

        Args:
            corp_codes: 고유번호 리스트 (최대 100개)
            years: 사업연도 리스트
            idx_cl_codes: 지표분류코드 리스트 (기본값: M210000 수익성지표)

        Returns:
            (values_map, names_map)
            - values_map: corp_code -> year -> { idx_code: value } (value는 소수, 예: 0.256 = 25.6%)
            - names_map: corp_code -> year -> { idx_code: idx_nm } (예: ROE, 영업수익경비율)
        """
        if not corp_codes:
            return {}, {}
        if idx_cl_codes is None:
            idx_cl_codes = ['M210000']
        corp_year_to_indicators: dict[str, dict[int, dict[str, float]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        corp_year_to_names: dict[str, dict[int, dict[str, str]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        for year in years:
            year_str = str(year)
            for idx_cl_code in idx_cl_codes:
                try:
                    raw_list = self.client.get_financial_indicators_multi(
                        corp_codes, year_str, reprt_code='11011', idx_cl_code=idx_cl_code
                    )
                except Exception as e:
                    logger.warning(
                        "다중회사 주요재무지표 API 실패 (배치 %s건, 연도 %s, 지표분류 %s): %s",
                        len(corp_codes), year_str, idx_cl_code, e,
                    )
                    continue
                if not raw_list:
                    continue
                for row in raw_list:
                    corp_code = (row.get('corp_code') or '').strip()
                    if not corp_code:
                        continue
                    try:
                        year_val = int(row.get('bsns_year', year))
                    except (ValueError, TypeError):
                        year_val = year
                    idx_code = (row.get('idx_code') or '').strip()
                    if not idx_code:
                        continue
                    idx_nm = (row.get('idx_nm') or '').strip() or None
                    raw_val = row.get('idx_val')
                    if raw_val is None:
                        raw_val = row.get('thstrm_amount')
                    if raw_val is None or (isinstance(raw_val, str) and not raw_val.strip()):
                        continue
                    try:
                        value_str = str(raw_val).replace(',', '').strip()
                        if not value_str:
                            continue
                        value = float(value_str)
                        # ROE(M211550)는 API가 퍼센트 단위(예: 3.395)로 주므로 소수로 저장 (÷100)
                        if idx_code == 'M211550':
                            value = value / 100.0
                        corp_year_to_indicators[corp_code][year_val][idx_code] = value
                        if idx_nm:
                            corp_year_to_names[corp_code][year_val][idx_code] = idx_nm
                    except (ValueError, TypeError):
                        continue
        result_values: dict[str, dict[int, dict[str, float]]] = {}
        result_names: dict[str, dict[int, dict[str, str]]] = {}
        for corp_code in corp_year_to_indicators:
            result_values[corp_code] = dict(corp_year_to_indicators[corp_code])
            result_names[corp_code] = dict(corp_year_to_names.get(corp_code, {}))
        return result_values, result_names

    def _process_single_quarter_basic(self, corp_code: str, rcept_no: str, reprt_code: str, quarter: int, mappings: dict):
        """
        단일 분기의 기본 지표 수집
        
        Args:
            corp_code: 고유번호
            rcept_no: 접수번호
            reprt_code: 보고서 코드
            quarter: 분기 (1, 2, 3)
            mappings: 지표 매핑 테이블
            
        Returns:
            (year, quarter, quarterly_data) 튜플 또는 None (실패 시)
        """
        # 접수번호에서 사업연도 추출 (접수번호 형식: YYYYMMDDXXXXXX)
        if len(rcept_no) < 4:
            return None
        
        rcept_year = int(rcept_no[:4])
        # 분기보고서는 해당 연도에 제출되므로, 접수연도가 사업연도
        # 1분기보고서도 접수연도가 사업연도 (예: 2025년 1분기 보고서는 2025년 5월에 제출)
        bsns_year = rcept_year
        
        year_str = str(bsns_year)
        
        # reprt_code가 비어있으면 분기별 코드로 설정
        if not reprt_code:
            quarterly_reprt_codes = {
                1: '11013',  # 1분기보고서
                2: '11012',  # 반기보고서
                3: '11014',  # 3분기보고서
            }
            reprt_code = quarterly_reprt_codes.get(quarter, '')
        
        # 분기보고서 재무제표 데이터 수집 (CFS 우선)
        for fs_div in ['CFS', 'OFS']:
            try:
                raw_data = self.client.get_financial_statement(
                    corp_code=corp_code,
                    bsns_year=year_str,
                    reprt_code=reprt_code,
                    fs_div=fs_div
                )
                
                if raw_data:
                    # FinancialStatementData 객체 생성
                    fs_data = FinancialStatementData(
                        year=year_str,
                        reprt_code=reprt_code,
                        fs_div=fs_div,
                        raw_data=raw_data
                    )
                    
                    # YearlyFinancialDataObject 생성 (분기 데이터용)
                    quarterly_data = YearlyFinancialDataObject(year=bsns_year)
                    
                    # 각 지표에 대해 매핑 및 추출
                    for indicator_key, mapping_config in mappings.items():
                        internal_field = mapping_config.get('internal_field')
                        dart_variants = mapping_config.get('dart_variants', [])
                        
                        value = 0
                        for variant in dart_variants:
                            normalized_variant = normalize_account_name(variant)
                            if normalized_variant in fs_data.normalized_account_index:
                                data = fs_data.normalized_account_index[normalized_variant]
                                amount = data.get('thstrm_amount', '0')
                                value = int(amount.replace(',', '')) if amount else 0
                                break
                        
                        if internal_field and hasattr(quarterly_data, internal_field):
                            current_value = getattr(quarterly_data, internal_field)
                            if current_value == 0:
                                setattr(quarterly_data, internal_field, value)
                    
                    return (bsns_year, quarter, quarterly_data, rcept_no)
            except Exception as e:
                if fs_div == 'CFS':
                    continue  # OFS도 시도
                # OFS도 실패
                pass
        
        return None
    
    def collect_quarterly_financial_data(self, corp_code: str, quarterly_reports: list) -> list:
        """
        분기보고서 재무 데이터 수집
        
        Args:
            corp_code: 고유번호 (8자리)
            quarterly_reports: 분기보고서 목록 (get_quarterly_reports_after_date 반환값)
            
        Returns:
            수집된 분기 데이터 리스트 [(year, quarter, quarterly_data, rcept_no), ...]
        """
        # 매핑표 로드
        mappings = self._load_indicator_mappings()
        
        # 병렬 처리로 각 분기별 데이터 수집
        quarterly_data_list = []
        
        with ThreadPoolExecutor(max_workers=min(len(quarterly_reports), 4)) as executor:
            # 모든 분기에 대한 작업 제출
            future_to_report = {
                executor.submit(
                    self._process_single_quarter_basic,
                    corp_code,
                    report['rcept_no'],
                    report['reprt_code'],
                    report['quarter'],
                    mappings
                ): report
                for report in quarterly_reports
            }
            
            # 완료된 작업 처리
            for future in as_completed(future_to_report):
                try:
                    result = future.result()
                    if result:
                        quarterly_data_list.append(result)
                except Exception:
                    # 보고서가 없어서 실패하는 경우이므로 출력하지 않음
                    pass

        return quarterly_data_list

    def collect_quarterly_data_for_save(
        self, corp_code: str, limit: int = 3
    ) -> list[tuple]:
        """
        분기보고서 수집 및 DB 저장용 데이터 반환 (비율 계산 포함).
        현재 날짜 기준 최근 limit개 분기보고서만 수집 (사업보고서 접수일 무관).

        Args:
            corp_code: 고유번호 (8자리)
            limit: 수집할 분기보고서 건수 (기본 3)

        Returns:
            [(year, quarter, quarterly_data, rcept_no, reprt_code), ...]
        """
        from apps.service.calculator import IndicatorCalculator

        quarterly_reports = self.client.get_recent_quarterly_reports(corp_code, limit=limit)
        if not quarterly_reports:
            return []

        raw_list = self.collect_quarterly_financial_data(
            corp_code, quarterly_reports
        )
        raw_list.sort(key=lambda x: (-x[0], -x[1]))

        rcept_no_to_reprt = {
            r.get("rcept_no"): r.get("reprt_code", "") for r in quarterly_reports
        }

        result = []
        for year, quarter, quarterly_data, rcept_no in raw_list:
            IndicatorCalculator.calculate_basic_financial_ratios_for_quarterly(
                quarterly_data
            )
            reprt_code = rcept_no_to_reprt.get(rcept_no, "")
            result.append((year, quarter, quarterly_data, rcept_no, reprt_code))
        return result

    # fill_financial_indicators() / _process_single_year_financial() 제거됨 (다중 get_financial_indicators_multi 로 통합)
    # 재무지표 계산 로직은 IndicatorCalculator.calculate_basic_financial_ratios()로 이동됨
    # 
    # 제거 이유:
    # - API 호출이 제거되어 단순 계산만 수행하게 되어 DartDataService의 역할이 아님
    # - 계산 로직은 IndicatorCalculator에 있는 것이 더 적절함
    #
    # 기존 재무지표 API 호출 코드 (주석처리):
    # - 매출총이익률, 판관비율은 기본 지표 API(fnlttSinglAcnt.json)에 해당 계정이 없어서 수집 불가
    # - 영업이익률은 기본 지표에서 계산, ROE는 DART 주요재무지표 M211550 사용
    # - API 호출 50% 감소 효과 (5개 연도 × 1회 = 5회 감소)


