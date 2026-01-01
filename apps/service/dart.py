"""
DART 데이터 수집 서비스
"""
import json
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from apps.dart.client import DartClient
from apps.models import FinancialStatementData, YearlyFinancialDataObject, CompanyFinancialObject
from apps.utils.utils import normalize_account_name
from apps.service.xbrl_parser import XbrlParser


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
    
    def collect_financial_data(self, corp_code: str, year: str):
        """
        단일 연도의 연간 보고서 재무제표 데이터 수집
        
        Args:
            corp_code: 고유번호 (8자리)
            year: 사업연도 (예: '2024')
        
        Returns:
            FinancialStatementData 객체 (단일, 실패 시 None)
        """
        # 연결재무제표 우선 시도, 없으면 별도재무제표
        for fs_div in ['CFS', 'OFS']:
            try:
                raw_data = self.client.get_financial_statement(
                    corp_code=corp_code,
                    bsns_year=year,
                    reprt_code='11011',  # 사업보고서
                    fs_div=fs_div
                )
                
                if raw_data:
                    return FinancialStatementData(
                        year=year,
                        reprt_code='11011',
                        fs_div=fs_div,
                        raw_data=raw_data
                    )
            except Exception as e:
                if fs_div == 'CFS':
                    continue
                else:
                    print(f"경고: {year}년 재무제표 수집 실패: {e}")
                    return None
        
        return None
    
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
    
    def _process_single_year_basic(self, corp_code: str, year: int, mappings: dict):
        """
        단일 연도의 기본 지표 처리 (병렬 처리용)
        
        Args:
            corp_code: 고유번호 (8자리)
            year: 연도
            mappings: 지표 매핑 테이블
            
        Returns:
            (year, yearly_data) 튜플 또는 None (실패 시)
        """
        year_str = str(year)
        
        # 단일 연도 재무제표 데이터 수집
        fs_data = self.collect_financial_data(corp_code, year_str)
        if not fs_data:
            return None  # 수집 실패 시 None 반환
        
        # YearlyFinancialData 객체 생성
        yearly_data = YearlyFinancialDataObject(year=year, corp_code=corp_code)
        
        # 각 지표에 대해 매핑 및 추출
        for indicator_key, mapping_config in mappings.items():
            internal_field = mapping_config.get('internal_field')
            dart_variants = mapping_config.get('dart_variants', [])
            
            # dart_variants를 순회하며 매칭 시도 (O(1) 조회)
            value = 0
            for variant in dart_variants:
                # 정규화된 계정명으로 매칭 시도
                normalized_variant = normalize_account_name(variant)
                
                # 정규화된 인덱스에서 직접 조회 (O(1))
                if normalized_variant in fs_data.normalized_account_index:
                    data = fs_data.normalized_account_index[normalized_variant]
                    amount = data.get('thstrm_amount', '0')
                    value = int(amount.replace(',', '')) if amount else 0
                    break  # 매칭 성공 시 종료
            
            # 객체에 직접 할당 (이미 값이 있으면 CFS 우선이므로 덮어쓰지 않음)
            if internal_field and hasattr(yearly_data, internal_field):
                current_value = getattr(yearly_data, internal_field)
                if current_value == 0:  # 아직 값이 없을 때만 할당
                    setattr(yearly_data, internal_field, value)
        
        return (year, yearly_data)
    
    def fill_basic_indicators(self, corp_code: str, years: list[int], company_data: CompanyFinancialObject):
        """
        CompanyFinancialObject의 yearly_data에 기본 지표를 채움 (in-place 수정)
        
        기본 지표: 매출액, 영업이익, 당기순이익, 자산총계, 자본총계, 유동부채
        
        Args:
            corp_code: 고유번호 (8자리)
            years: 수집할 연도 리스트 (예: [2020, 2021, 2022, 2023, 2024])
            company_data: 채울 CompanyFinancialObject 객체
        """
        # 매핑표 로드
        mappings = self._load_indicator_mappings()
        
        # 병렬 처리로 각 연도별 데이터 수집
        yearly_data_list = []
        with ThreadPoolExecutor(max_workers=len(years)) as executor:
            # 모든 연도에 대한 작업 제출
            future_to_year = {
                executor.submit(self._process_single_year_basic, corp_code, year, mappings): year
                for year in years
            }
            
            # 완료된 작업 처리
            for future in as_completed(future_to_year):
                try:
                    result = future.result()
                    if result:
                        yearly_data_list.append(result)
                except Exception as e:
                    year = future_to_year[future]
                    print(f"경고: {year}년 기본 지표 수집 중 예외 발생: {e}")
        
        # 연도 순서대로 정렬하여 추가
        yearly_data_list.sort(key=lambda x: x[0])
        for year, yearly_data in yearly_data_list:
            company_data.yearly_data.append(yearly_data)
    
    # XBRL 데이터 수집 중단: 표본이 너무 적어서 데이터화를 못할듯하여 일단 중단
    # def collect_xbrl_indicators(self, corp_code: str, years: list[int], company_data: CompanyFinancialObject):
    #     """
    #     XBRL 파일에서 추가 지표 수집
    #     
    #     Args:
    #         corp_code: 고유번호 (8자리)
    #         years: 수집할 연도 리스트
    #         company_data: 채울 CompanyFinancialObject 객체 (in-place 수정)
    #     """
    #     parser = XbrlParser()
    #     
    #     # 각 연도별로 처리
    #     for year in years:
    #         year_str = str(year)
    #         
    #         # 해당 연도의 YearlyFinancialData 찾기
    #         yearly_data = None
    #         for yd in company_data.yearly_data:
    #             if yd.year == year:
    #                 yearly_data = yd
    #                 break
    #         
    #         # YearlyFinancialData가 없으면 생성
    #         if yearly_data is None:
    #             yearly_data = YearlyFinancialData(year=year, corp_code=corp_code)
    #             company_data.yearly_data.append(yearly_data)
    #        
    #         try:
    #             # 사업보고서 접수번호 조회
    #             try:
    #                 rcept_no = self.client.get_annual_report_rcept_no(corp_code, year_str)
    #                 if not rcept_no:
    #                     continue
    #             except Exception as e:
    #                 continue
    #             
    #             # XBRL 다운로드 및 사업보고서 XML 추출
    #             xml_content = self.client.download_xbrl_and_extract_annual_report(rcept_no)
    #             
    #             # XBRL 파싱
    #             xbrl_data = parser.parse_xbrl_file(xml_content)
    #             
    #             # YearlyFinancialData에 채우기
    #             yearly_data.tangible_asset_acquisition = xbrl_data.get('tangible_asset_acquisition', 0)
    #             yearly_data.intangible_asset_acquisition = xbrl_data.get('intangible_asset_acquisition', 0)
    #             yearly_data.cfo = xbrl_data.get('cfo', 0)
    #             yearly_data.equity = xbrl_data.get('equity', 0)
    #             yearly_data.cash_and_cash_equivalents = xbrl_data.get('cash_and_cash_equivalents', 0)
    #             yearly_data.short_term_borrowings = xbrl_data.get('short_term_borrowings', 0)
    #             yearly_data.current_portion_of_long_term_borrowings = xbrl_data.get('current_portion_of_long_term_borrowings', 0)
    #             yearly_data.long_term_borrowings = xbrl_data.get('long_term_borrowings', 0)
    #             yearly_data.bonds = xbrl_data.get('bonds', 0)
    #             yearly_data.lease_liabilities = xbrl_data.get('lease_liabilities', 0)
    #             yearly_data.finance_costs = xbrl_data.get('finance_costs', 0)
    #             
    #         except Exception as e:
    #             # 예외 발생 시에도 계속 진행 (다른 연도 수집 계속)
    #             continue
    
    def _process_single_year_financial(self, corp_code: str, year: int, indicator_mappings: dict):
        """
        단일 연도의 재무지표 처리 (병렬 처리용)
        
        Args:
            corp_code: 고유번호 (8자리)
            year: 연도
            indicator_mappings: 재무지표 코드 매핑
            
        Returns:
            (year, results_dict) 튜플 또는 None (실패 시)
            results_dict: {field_name: value} 형태의 딕셔너리
        """
        year_str = str(year)
        
        try:
            # 재무지표 API 호출
            indicators_data = self.client.get_financial_indicators(
                corp_code=corp_code,
                bsns_year=year_str,
                reprt_code='11011'  # 사업보고서
            )
            
            if not indicators_data:
                return None
            
            # 각 지표 코드에 대해 매핑
            results = {}
            found_indicators = []
            for idx_code, field_name in indicator_mappings.items():
                # 해당 idx_code를 가진 지표 찾기
                found = False
                for indicator in indicators_data:
                    if indicator.get('idx_code') == idx_code:
                        found = True
                        found_indicators.append(idx_code)
                        # idx_val 값 추출 (API 문서에 따르면 idx_val 사용)
                        # thstrm_amount도 확인 (하위 호환성)
                        idx_val = indicator.get('idx_val')
                        thstrm_amount = indicator.get('thstrm_amount')
                        
                        # idx_val 우선, 없으면 thstrm_amount 사용
                        value_str = idx_val if idx_val is not None else thstrm_amount
                        
                        if value_str is not None and value_str != '' and str(value_str).strip() != '':
                            try:
                                # 문자열로 변환 후 쉼표 제거 및 float 변환
                                value_str_clean = str(value_str).replace(',', '').strip()
                                if value_str_clean:
                                    value = float(value_str_clean)
                                    # DART API는 백분율로 반환하므로 소수로 변환 (예: 30.335% -> 0.30335)
                                    value = value / 100.0
                                    results[field_name] = value
                                else:
                                    print(f"  경고: {year}년 {idx_code} 값이 비어있습니다.")
                            except (ValueError, AttributeError) as ve:
                                # 변환 실패 시 0으로 유지
                                print(f"  경고: {year}년 {idx_code} 값 변환 실패: {value_str}, 오류: {ve}")
                        else:
                            print(f"  경고: {year}년 {idx_code} 값이 비어있습니다. (idx_val: {idx_val}, thstrm_amount: {thstrm_amount})")
                        break
                
                if not found:
                    print(f"  경고: {year}년 {idx_code} 지표를 찾을 수 없습니다.")
            
            if found_indicators:
                print(f"  ✓ {year}년 재무지표 수집 완료: {', '.join(found_indicators)}")
            
            return (year, results)
                        
        except Exception as e:
            # 예외 발생 시에도 계속 진행 (다른 연도 수집 계속)
            print(f"  오류: {year}년 재무지표 수집 중 예외 발생: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    # fill_financial_indicators() 메서드 제거됨
    # 재무지표 계산 로직은 IndicatorCalculator.calculate_basic_financial_ratios()로 이동됨
    # 
    # 제거 이유:
    # - API 호출이 제거되어 단순 계산만 수행하게 되어 DartDataService의 역할이 아님
    # - 계산 로직은 IndicatorCalculator에 있는 것이 더 적절함
    #
    # 기존 재무지표 API 호출 코드 (주석처리):
    # - 매출총이익률, 판관비율은 기본 지표 API(fnlttSinglAcnt.json)에 해당 계정이 없어서 수집 불가
    # - 총자산영업이익률, ROE는 기본 지표에서 계산 가능하여 API 호출 제거
    # - API 호출 50% 감소 효과 (5개 연도 × 1회 = 5회 감소)


