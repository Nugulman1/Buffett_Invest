"""
DART OpenDART API 클라이언트
"""
import logging
import re
import time
import requests
import zipfile
import io
import xml.etree.ElementTree as ET
import json
from datetime import date
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class DartClient:
    """DART OpenDART API 클라이언트"""
    
    BASE_URL = "https://opendart.fss.or.kr/api"
    
    # 종목코드 → corp_code 매핑 캐시 (클래스 변수)
    _corp_code_mapping_cache = {}
    
    # API 호출 횟수 추적 (클래스 변수)
    _api_call_count = 0
    
    # 일별 통계 업데이트 플래그 (성능 최적화: 배치 업데이트)
    _last_stats_update_date = None
    _pending_dart_calls = 0
    
    def __init__(self, api_key=None):
        """
        DART 클라이언트 초기화
        
        Args:
            api_key: DART API 키 (없으면 settings에서 가져옴)
        """
        self.api_key = api_key or settings.DART_API_KEY
        if not self.api_key:
            raise ValueError("DART_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    
    def _calculate_wait_time(self, attempt, response=None):
        """
        재시도 대기 시간 계산
        
        Args:
            attempt: 현재 재시도 횟수 (0부터 시작)
            response: Response 객체 (있을 수도, 없을 수도)
            
        Returns:
            대기 시간 (초)
        """
        # Rate Limit (429)인 경우 Retry-After 헤더 확인
        if response and hasattr(response, 'status_code') and response.status_code == 429:
            retry_after = response.headers.get('Retry-After')
            if retry_after:
                try:
                    return int(retry_after)
                except ValueError:
                    # Retry-After가 유효하지 않으면 exponential backoff
                    pass
        
        # Exponential Backoff: 2^attempt 초 대기 (1초, 2초, 4초...)
        return 2 ** attempt
    
    def _should_retry(self, attempt, max_retries, response=None, retryable_codes=None):
        """
        재시도 가능 여부 판단
        
        Args:
            attempt: 현재 재시도 횟수 (0부터 시작)
            max_retries: 최대 재시도 횟수
            response: Response 객체 (있을 수도, 없을 수도)
            retryable_codes: 재시도 가능한 HTTP 상태 코드 집합
            
        Returns:
            재시도 가능하면 True, 아니면 False
        """
        # 마지막 시도면 재시도 안 함
        if attempt >= max_retries:
            return False
        
        # response가 있으면 (HTTPError) → status_code 확인
        if response and hasattr(response, 'status_code'):
            return response.status_code in (retryable_codes or {})
        
        # response가 없으면 (네트워크 오류) → 재시도 가능
        return True
    
    def _make_request(self, endpoint, params=None, return_binary=False, max_retries=None, timeout=None):
        """
        API 요청 공통 메서드 (재시도 로직 포함)
        
        Args:
            endpoint: API 엔드포인트
            params: 요청 파라미터
            return_binary: True면 바이너리 데이터 반환 (XBRL 다운로드용)
            max_retries: 최대 재시도 횟수 (None이면 settings에서 가져옴)
            timeout: API 요청 타임아웃 (None이면 settings에서 가져옴)
            
        Returns:
            API 응답 데이터 (JSON 또는 바이너리)
        """
        # 설정 파일에서 가져오기 (파라미터가 있으면 우선)
        if max_retries is None:
            max_retries = settings.DATA_COLLECTION['API_MAX_RETRIES']
        if timeout is None:
            timeout = settings.DATA_COLLECTION['API_TIMEOUT']
        
        url = f"{self.BASE_URL}/{endpoint}"
        
        if params is None:
            params = {}
        
        params['crtfc_key'] = self.api_key
        
        # 재시도 가능한 HTTP 상태 코드 (일시적 오류)
        retryable_status_codes = {429, 500, 502, 503, 504}
        
        for attempt in range(max_retries + 1):  # 0, 1, 2, 3 (총 4번 시도)
            try:
                # API 호출 횟수 증가
                DartClient._api_call_count += 1
                
                # 일별 API 호출 통계 업데이트
                DartClient._update_daily_stats()
                
                response = requests.get(url, params=params, timeout=timeout)
                
                # 성공한 경우
                if response.status_code == 200:
                    # API 호출 사이 지연 추가 (Rate Limiting 방지)
                    api_delay = settings.DATA_COLLECTION.get('API_DELAY', 1.0)
                    if api_delay > 0:
                        time.sleep(api_delay)
                    
                    if return_binary:
                        return response.content
                    return response.json()
                
                # 재시도 가능한 오류인지 확인
                if self._should_retry(attempt, max_retries, response, retryable_status_codes):
                    # 재시도
                    wait_time = self._calculate_wait_time(attempt, response)
                    time.sleep(wait_time)
                    continue
                else:
                    # 재시도 불가능한 오류 (400, 401, 404 등)
                    response.raise_for_status()
                    
            except requests.exceptions.RequestException as e:
                # 모든 네트워크/HTTP 오류 통합 처리
                response = getattr(e, 'response', None)
                
                # 재시도 가능 여부 판단
                if self._should_retry(attempt, max_retries, response, retryable_status_codes):
                    # 재시도
                    wait_time = self._calculate_wait_time(attempt, response)
                    time.sleep(wait_time)
                    continue
                else:
                    # 재시도 불가능
                    if isinstance(e, requests.exceptions.HTTPError):
                        # HTTPError는 원래 예외 유지 (상태 코드, 에러 메시지 등 보존)
                        raise
                    else:
                        # 네트워크 오류는 새로운 예외 생성 (상세 정보 포함)
                        raise Exception(f"DART API 요청 실패 (최대 {max_retries}회 재시도 후 실패): {str(e)}")
    
    def get_company_info(self, corp_code):
        """
        기업 정보 조회
        
        Args:
            corp_code: 고유번호 (8자리)
            
        Returns:
            기업 정보 데이터
        """
        return self._make_request("company.json", params={'corp_code': corp_code})
    
    def load_corp_code_xml(self):
        """
        기업 고유번호 XML 파일을 다운로드하여 캐시에 저장
        
        한 번만 다운로드하여 모든 종목코드 → corp_code 매핑을 메모리에 저장
        """
        if self._corp_code_mapping_cache:
            return  # 이미 로드됨
        
        try:
            # 기업 고유번호 XML 파일 다운로드 (_make_request 사용하여 재시도 로직 적용)
            zip_content = self._make_request("corpCode.xml", return_binary=True)
            
            # ZIP 파일 압축 해제
            with zipfile.ZipFile(io.BytesIO(zip_content)) as z:
                xml_content = z.read('CORPCODE.xml')
            
            # XML 파싱
            root = ET.fromstring(xml_content)
            
            # 모든 종목코드 → corp_code 매핑을 캐시에 저장
            for corp in root:
                stock_code_elem = corp.find('stock_code')
                corp_code_elem = corp.find('corp_code')
                if stock_code_elem is not None and stock_code_elem.text and corp_code_elem is not None:
                    stock_code = stock_code_elem.text.strip()
                    corp_code = corp_code_elem.text.strip()
                    if stock_code and corp_code:
                        self._corp_code_mapping_cache[stock_code] = corp_code
        except Exception as e:
            raise Exception(f"기업 고유번호 XML 로드 실패: {str(e)}")
    
    @classmethod
    def _update_daily_stats(cls):
        """일별 API 호출 통계 업데이트 (배치 처리로 성능 최적화)"""
        try:
            from django.apps import apps as django_apps
            ApiCallStatsModel = django_apps.get_model('apps', 'ApiCallStats')
            
            today = date.today()
            
            # 날짜가 바뀌었거나 처음 호출이면 DB 업데이트
            if cls._last_stats_update_date != today:
                # 대기 중인 호출 횟수 저장
                if cls._pending_dart_calls > 0:
                    stats, _ = ApiCallStatsModel.objects.get_or_create(
                        date=today,
                        defaults={'dart_calls': 0, 'ecos_calls': 0}
                    )
                    stats.dart_calls += cls._pending_dart_calls
                    stats.save(update_fields=['dart_calls', 'updated_at'])
                    cls._pending_dart_calls = 0
                
                cls._last_stats_update_date = today
            
            # 대기 중인 호출 횟수 증가 (배치 업데이트)
            cls._pending_dart_calls += 1
            
            # 10회마다 DB 업데이트 (성능 최적화)
            if cls._pending_dart_calls >= 10:
                stats, _ = ApiCallStatsModel.objects.get_or_create(
                    date=today,
                    defaults={'dart_calls': 0, 'ecos_calls': 0}
                )
                stats.dart_calls += cls._pending_dart_calls
                stats.save(update_fields=['dart_calls', 'updated_at'])
                cls._pending_dart_calls = 0
                
        except Exception:
            # DB 오류 시 무시 (통계 수집 실패해도 API 호출은 계속)
            pass
    
    @classmethod
    def flush_daily_stats(cls):
        """대기 중인 통계를 DB에 저장 (프로그램 종료 시 호출)"""
        try:
            from django.apps import apps as django_apps
            ApiCallStatsModel = django_apps.get_model('apps', 'ApiCallStats')
            
            if cls._pending_dart_calls > 0:
                today = date.today()
                stats, _ = ApiCallStatsModel.objects.get_or_create(
                    date=today,
                    defaults={'dart_calls': 0, 'ecos_calls': 0}
                )
                stats.dart_calls += cls._pending_dart_calls
                stats.save(update_fields=['dart_calls', 'updated_at'])
                cls._pending_dart_calls = 0
        except Exception:
            pass
    
    def _get_corp_code_by_stock_code(self, stock_code):
        """
        종목코드로 기업 고유번호(corp_code) 조회
        
        XML 캐시를 사용하여 한 번만 다운로드하고 재사용
        
        Args:
            stock_code: 종목코드 (6자리, 예: '005930')
            
        Returns:
            corp_code (고유번호) 또는 None
        """
        # 캐시가 비어있으면 먼저 로드
        if not self._corp_code_mapping_cache:
            self.load_corp_code_xml()
        
        # 캐시에서 조회
        return self._corp_code_mapping_cache.get(stock_code)
    
    def get_company_by_stock_code(self, stock_code):
        """
        종목코드로 기업 정보 조회
        
        Args:
            stock_code: 종목코드 (6자리, 예: '005930')
            
        Returns:
            기업 정보 데이터 (dict)
            - corp_name: 기업명
            - corp_code: 고유번호
            - induty_code: 산업코드 (industry_code로 매핑 가능)
        """
        # 1단계: 종목코드로 corp_code 찾기
        corp_code = self._get_corp_code_by_stock_code(stock_code)
        if not corp_code:
            raise ValueError(f"종목코드 {stock_code}에 해당하는 기업을 찾을 수 없습니다.")
        
        # 2단계: corp_code로 기업 정보 조회
        company_info = self.get_company_info(corp_code)
        
        # 3단계: 응답 검증
        if isinstance(company_info, dict) and company_info.get('status') != '000':
            raise Exception(f"기업 정보 조회 실패: {company_info.get('message', '알 수 없는 오류')}")
        
        return company_info
    
    def get_company_basic_info(self, stock_code):
        """
        종목코드로 기업 기본 정보 조회 (corp_name, corp_code, industry_code)
        
        Args:
            stock_code: 종목코드 (6자리, 예: '005930')
            
        Returns:
            dict: {
                'corp_name': str,      # 기업명
                'corp_code': str,       # 고유번호
                'industry_code': str   # 산업코드 (induty_code를 industry_code로 매핑)
            }
        """
        company_info = self.get_company_by_stock_code(stock_code)
        
        return {
            'corp_name': company_info.get('corp_name', ''),
            'corp_code': company_info.get('corp_code', ''),
            'industry_code': company_info.get('induty_code', '')  # induty_code를 industry_code로 매핑
        }
    
    def get_financial_statement(self, corp_code, bsns_year, reprt_code='11011', fs_div='CFS'):
        """
        재무제표 조회 (원시 금액 데이터)
        
        재무제표의 계정별 금액 데이터를 조회합니다.
        - API: fnlttSinglAcnt.json
        - 데이터 형태: 계정명(account_nm)과 금액(thstrm_amount) - 원 단위
        - 예시: {"account_nm": "매출액", "thstrm_amount": "100,000,000,000"} → 1000억원
        
        get_financial_indicators()와의 차이:
        - 이 메서드: 원시 금액 데이터 (매출액 1000억원, 영업이익 100억원 등)
        - get_financial_indicators(): 계산된 비율 지표 (매출총이익률 20%, ROE 15% 등)
        
        Args:
            corp_code: 기업 고유번호 (8자리)
            bsns_year: 사업연도 (예: '2023')
            reprt_code: 보고서 코드 ('11011': 사업보고서)
            fs_div: 재무제표 구분 ('CFS': 연결, 'OFS': 별도)
            
        Returns:
            재무제표 데이터 (list) - 각 항목은 계정명과 금액을 포함
        """
        params = {
            'corp_code': corp_code,
            'bsns_year': bsns_year,
            'reprt_code': reprt_code,
            'fs_div': fs_div
        }
        
        result = self._make_request("fnlttSinglAcnt.json", params=params)
        
        # 응답 검증
        if isinstance(result, dict) and result.get('status') != '000':
            # "조회된 데이타가 없습니다" 메시지도 빈 리스트로 처리 (예외 대신)
            message = result.get('message', '알 수 없는 오류')
            if '조회된 데이타가 없습니다' in message or '데이터가 없습니다' in message:
                return []
            raise Exception(f"재무제표 조회 실패: {message}")
        
        # list 필드에서 재무제표 데이터 반환
        financial_list = result.get('list', [])
        
        # 빈 리스트인 경우도 정상 반환 (호출자가 처리)
        return financial_list if isinstance(financial_list, list) else []
    
    def get_report_list(self, corp_code, bgn_de, end_de, last_reprt_at='N', page_no=1, page_count=1000):
        """
        공시보고서 목록 조회
        
        Args:
            corp_code: 기업 고유번호 (8자리)
            bgn_de: 시작일자 (YYYYMMDD)
            end_de: 종료일자 (YYYYMMDD)
            last_reprt_at: 최종보고서만 조회 여부 ('Y' 또는 'N')
            page_no: 페이지 번호 (기본값: 1)
            page_count: 페이지당 건수 (기본값: 100, 최대: 1000)
            
        Returns:
            보고서 목록 데이터
        """
        params = {
            'corp_code': corp_code,
            'bgn_de': bgn_de,
            'end_de': end_de,
            'last_reprt_at': last_reprt_at,
            'page_no': page_no,
            'page_count': min(page_count, 1000)  # 최대 1000건으로 제한
        }
        
        result = self._make_request("list.json", params=params)
        
        if isinstance(result, dict) and result.get('status') != '000':
            raise Exception(f"보고서 목록 조회 실패: {result.get('message', '알 수 없는 오류')}")
        
        # total_page 정보를 포함하여 반환 (페이지네이션을 위해)
        return {
            'list': result.get('list', []),
            'total_page': result.get('total_page', 1),
            'total_count': result.get('total_count', 0)
        }

    def get_annual_report_rcept_no(self, corp_code: str, year: str) -> str:
        """
        해당 연도의 사업보고서 접수번호 조회
        
        Args:
            corp_code: 고유번호 (8자리)
            year: 사업연도 (예: '2024')
            
        Returns:
            접수번호 (14자리) 또는 None
        """
        # 연간보고서는 다음 해에 발행되므로 다음 해 기간으로 검색
        # 사업보고서는 보통 다음 해 3월~4월에 제출되므로, 3월~4월만 검색
        next_year = int(year) + 1
        bgn_de = f"{next_year}0301"  # 다음 해 3월 1일부터
        end_de = f"{next_year}0430"   # 다음 해 4월 30일까지
        
        try:
            # 모든 보고서 조회 (last_reprt_at='N') 및 페이지당 1000건으로 조회 (최대값)
            # 페이지네이션 처리: 여러 페이지가 있을 수 있으므로 모든 페이지를 조회
            all_reports = []
            page_no = 1
            total_page = 1
            while True:
                result = self.get_report_list(corp_code, bgn_de, end_de, last_reprt_at='N', page_no=page_no, page_count=1000)
                report_list = result.get('list', []) if isinstance(result, dict) else []
                total_page = result.get('total_page', 1) if isinstance(result, dict) else 1
                
                if not report_list:
                    break
                all_reports.extend(report_list)
                # total_page를 확인하여 모든 페이지를 조회
                if page_no >= total_page:
                    break
                page_no += 1
            report_list = all_reports
            
            if not report_list:
                return None
            
            # 사업보고서 찾기 (report_nm에 "사업보고서" 포함)
            for report in report_list:
                report_nm = report.get('report_nm', '')
                
                # report_nm에 "사업보고서"가 포함되어 있는지 확인
                if '사업보고서' in report_nm:
                    rcept_no = report.get('rcept_no', '')
                    if rcept_no and len(rcept_no) >= 4:
                        rcept_year = rcept_no[:4]
                        # 접수번호의 연도가 다음 해와 일치하면 해당 연도의 사업보고서로 간주
                        if rcept_year == str(next_year):
                            return rcept_no
            
            return None
            
        except Exception as e:
            logger.exception("%s년 사업보고서 접수번호 조회 실패: %s", year, e)
            return None
    
    def get_latest_annual_report_date(self, corp_code: str) -> str | None:
        """
        가장 최근 사업보고서의 접수일자 조회
        
        Args:
            corp_code: 고유번호 (8자리)
            
        Returns:
            접수일자 (YYYYMMDD 형식) 또는 None
        """
        from datetime import datetime
        
        # 최근 5년 동안 사업보고서 찾기
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        # 현재 월이 4월 이후면 작년 사업보고서가 이미 제출됨
        if current_month >= 4:
            latest_year = current_year - 1
        else:
            latest_year = current_year - 2
        
        # 최근 5년 동안 찾기
        for year_offset in range(5):
            try_year = latest_year - year_offset
            rcept_no = self.get_annual_report_rcept_no(corp_code, str(try_year))
            
            if rcept_no:
                # 접수번호에서 접수일자 추출 (접수번호 형식: YYYYMMDDXXXXXX)
                if len(rcept_no) >= 8:
                    rcept_date = rcept_no[:8]  # YYYYMMDD
                    return rcept_date
        
        return None
    
    @staticmethod
    def _is_actual_quarterly_report(report_nm: str) -> bool:
        """report_nm이 실제 분기(재무)보고서인지 여부. 3분기배당·수시공시 등은 제외."""
        if not report_nm:
            return False
        return (
            "분기보고서" in report_nm
            or "1분기보고서" in report_nm
            or "반기보고서" in report_nm
            or "3분기보고서" in report_nm
        )

    def _log_quarterly_reports_debug(
        self,
        corp_code: str,
        bgn_de: str,
        end_date: str,
        all_reports: list,
        quarterly_reports: list,
        skipped_quarterly: list,
    ) -> None:
        """분기보고서 조회 결과를 디버깅용으로 로그 출력."""
        lines = [
            "",
            "=" * 60,
            "[분기보고서 조회 디버그]",
            f"  corp_code: {corp_code}  |  조회 구간: {bgn_de} ~ {end_date}",
            f"  DART 조회 전체 건수: {len(all_reports)}",
            f"  분기로 인식·수집: {len(quarterly_reports)}건  |  분기로 인식했으나 제외: {len(skipped_quarterly)}건",
            "-" * 60,
        ]
        if quarterly_reports:
            lines.append("  [수집 대상 분기보고서]")
            for r in quarterly_reports:
                qname = {1: "1분기", 2: "반기", 3: "3분기"}.get(r["quarter"], str(r["quarter"]))
                lines.append(f"    {r['rcept_dt']}  {qname}  reprt_code={r.get('reprt_code','')}  |  {r.get('report_nm', '')[:50]}")
        if skipped_quarterly:
            lines.append("  [분기로 인식했으나 제외]")
            for s in skipped_quarterly[:10]:
                qname = {1: "1분기", 2: "반기", 3: "3분기"}.get(s["quarter"], str(s["quarter"]))
                lines.append(f"    {s.get('rcept_dt','')}  {qname}  |  {s.get('reason','')}  |  {s.get('report_nm','')[:40]}")
            if len(skipped_quarterly) > 10:
                lines.append(f"    ... 외 {len(skipped_quarterly) - 10}건")
        lines.extend(["=" * 60, ""])
        logger.info("\n".join(lines))

    def get_quarterly_reports_after_date(self, corp_code: str, after_date: str) -> list:
        """
        특정 날짜 이후의 분기보고서 목록 조회
        
        Args:
            corp_code: 고유번호 (8자리)
            after_date: 기준 날짜 (YYYYMMDD 형식)
            
        Returns:
            분기보고서 목록 (접수일자 기준 내림차순 정렬)
        """
        from datetime import datetime
        
        # 현재 날짜까지 조회
        end_date = datetime.now().strftime('%Y%m%d')
        
        # 분기보고서 코드 매핑
        quarterly_codes = {
            '11013': 1,  # 1분기보고서
            '11012': 2,  # 반기보고서
            '11014': 3,  # 3분기보고서
        }
        
        try:
            # 모든 보고서 조회
            all_reports = []
            page_no = 1
            total_page = 1
            
            while True:
                result = self.get_report_list(corp_code, after_date, end_date, last_reprt_at='N', page_no=page_no, page_count=1000)
                report_list = result.get('list', []) if isinstance(result, dict) else []
                total_page = result.get('total_page', 1) if isinstance(result, dict) else 1
                
                if not report_list:
                    break
                all_reports.extend(report_list)
                if page_no >= total_page:
                    break
                page_no += 1
            
            # 분기보고서만 필터링: reprt_code 우선(11013/11012/11014), 없으면 report_nm으로 판별
            # after_date는 DART API에 조회 구간(bgn_de~end_de)으로 필요 + "최근 사업보고서 이후" 분기만 수집
            quarterly_reports = []
            skipped_quarterly = []  # 분기로 인식했으나 제외된 건 (디버깅용)
            for report in all_reports:
                report_nm = report.get('report_nm', '') or ''
                reprt_code = (report.get('reprt_code') or '').strip()
                rcept_dt = report.get('rcept_dt', '')
                quarter = None
                detected_reprt_code = None

                # 1) reprt_code로 분기보고서 여부·분기 판별 (DART가 주면 가장 확실함)
                if reprt_code in quarterly_codes:
                    if self._is_actual_quarterly_report(report_nm):
                        quarter = quarterly_codes[reprt_code]
                        detected_reprt_code = reprt_code
                    else:
                        # reprt_code는 분기코드지만 report_nm이 3분기배당·수시공시 등 실제 분기보고서가 아님
                        skipped_quarterly.append({
                            "report_nm": report_nm,
                            "rcept_dt": rcept_dt[:8] if rcept_dt and len(rcept_dt) >= 8 else rcept_dt or "(없음)",
                            "quarter": quarterly_codes[reprt_code],
                            "reason": "report_nm이 분기보고서가 아님(3분기배당 등 제외)",
                        })
                else:
                    # 2) report_nm으로 판별 (reprt_code 비어있거나 분기코드가 아닐 때)
                    quarterly_match = re.search(r'분기보고서\s*\((\d{4})\.(\d{2})\)', report_nm)
                    if quarterly_match:
                        year = int(quarterly_match.group(1))
                        month = int(quarterly_match.group(2))
                        # 분기 종료월(3,6,9) 또는 제출월(5,8,11) 모두 허용
                        if month in (3, 5):
                            quarter, detected_reprt_code = 1, '11013'
                        elif month in (6, 8):
                            quarter, detected_reprt_code = 2, '11012'
                        elif month in (9, 11):
                            quarter, detected_reprt_code = 3, '11014'
                    elif '1분기보고서' in report_nm or '1분기' in report_nm or '제1분기' in report_nm:
                        quarter, detected_reprt_code = 1, '11013'
                    elif '반기보고서' in report_nm or '반기' in report_nm or '제2분기' in report_nm or '1·2분기' in report_nm:
                        quarter, detected_reprt_code = 2, '11012'
                    elif '3분기보고서' in report_nm or '3분기' in report_nm or '제3분기' in report_nm:
                        quarter, detected_reprt_code = 3, '11014'
                    # report_nm으로만 매칭된 경우 실제 분기보고서인지 한 번 더 검사 (3분기배당 등 제외)
                    if quarter is not None and not self._is_actual_quarterly_report(report_nm):
                        skipped_quarterly.append({
                            "report_nm": report_nm,
                            "rcept_dt": rcept_dt[:8] if rcept_dt and len(rcept_dt) >= 8 else rcept_dt or "(없음)",
                            "quarter": quarter,
                            "reason": "report_nm이 분기보고서가 아님(3분기배당 등 제외)",
                        })
                        quarter, detected_reprt_code = None, None

                if quarter is not None:
                    # 접수일자 추출
                    if rcept_dt and len(rcept_dt) >= 8:
                        rcept_date = rcept_dt[:8]  # YYYYMMDD
                        if rcept_date > after_date:
                            quarterly_reports.append({
                                'rcept_no': report.get('rcept_no', ''),
                                'rcept_dt': rcept_date,
                                'reprt_code': detected_reprt_code or '',
                                'report_nm': report_nm,
                                'quarter': quarter,
                            })
                        else:
                            skipped_quarterly.append({
                                'report_nm': report_nm,
                                'rcept_dt': rcept_date,
                                'quarter': quarter,
                                'reason': f"rcept_dt({rcept_date}) <= after_date({after_date})",
                            })
                    else:
                        skipped_quarterly.append({
                            'report_nm': report_nm,
                            'rcept_dt': rcept_dt or '(없음)',
                            'quarter': quarter,
                            'reason': 'rcept_dt 길이 부족',
                        })

            # 접수일자 기준 내림차순 정렬 (가장 최근 것부터)
            quarterly_reports.sort(key=lambda x: x['rcept_dt'], reverse=True)

            self._log_quarterly_reports_debug(
                corp_code, after_date, end_date,
                all_reports, quarterly_reports, skipped_quarterly,
            )
            return quarterly_reports

        except Exception as e:
            logger.warning("분기보고서 목록 조회 실패: %s", e)
            return []

    def get_recent_quarterly_reports(self, corp_code: str, limit: int = 3) -> list:
        """
        현재 날짜 기준 최근 분기보고서 N건 조회 (사업보고서 접수일 무관).

        Args:
            corp_code: 고유번호 (8자리)
            limit: 가져올 분기보고서 건수 (기본 3)

        Returns:
            분기보고서 목록 (접수일자 내림차순, 최대 limit건)
        """
        from datetime import datetime, timedelta

        end_date = datetime.now().strftime('%Y%m%d')
        bgn_de = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')  # 최근 1년

        quarterly_codes = {
            '11013': 1,
            '11012': 2,
            '11014': 3,
        }

        try:
            all_reports = []
            page_no = 1
            total_page = 1
            while True:
                result = self.get_report_list(
                    corp_code, bgn_de, end_date, last_reprt_at='N', page_no=page_no, page_count=1000
                )
                report_list = result.get('list', []) if isinstance(result, dict) else []
                total_page = result.get('total_page', 1) if isinstance(result, dict) else 1
                if not report_list:
                    break
                all_reports.extend(report_list)
                if page_no >= total_page:
                    break
                page_no += 1

            quarterly_reports = []
            skipped_quarterly = []
            for report in all_reports:
                report_nm = report.get('report_nm', '') or ''
                reprt_code = (report.get('reprt_code') or '').strip()
                rcept_dt = report.get('rcept_dt', '')
                quarter = None
                detected_reprt_code = None

                if reprt_code in quarterly_codes:
                    if self._is_actual_quarterly_report(report_nm):
                        quarter = quarterly_codes[reprt_code]
                        detected_reprt_code = reprt_code
                    else:
                        skipped_quarterly.append({
                            "report_nm": report_nm,
                            "rcept_dt": rcept_dt[:8] if rcept_dt and len(rcept_dt) >= 8 else rcept_dt or "(없음)",
                            "quarter": quarterly_codes[reprt_code],
                            "reason": "report_nm이 분기보고서가 아님(3분기배당 등 제외)",
                        })
                else:
                    quarterly_match = re.search(r'분기보고서\s*\((\d{4})\.(\d{2})\)', report_nm)
                    if quarterly_match:
                        month = int(quarterly_match.group(2))
                        if month in (3, 5):
                            quarter, detected_reprt_code = 1, '11013'
                        elif month in (6, 8):
                            quarter, detected_reprt_code = 2, '11012'
                        elif month in (9, 11):
                            quarter, detected_reprt_code = 3, '11014'
                    elif '1분기보고서' in report_nm or '1분기' in report_nm or '제1분기' in report_nm:
                        quarter, detected_reprt_code = 1, '11013'
                    elif '반기보고서' in report_nm or '반기' in report_nm or '제2분기' in report_nm or '1·2분기' in report_nm:
                        quarter, detected_reprt_code = 2, '11012'
                    elif '3분기보고서' in report_nm or '3분기' in report_nm or '제3분기' in report_nm:
                        quarter, detected_reprt_code = 3, '11014'
                    # report_nm으로만 매칭된 경우 실제 분기보고서인지 한 번 더 검사 (3분기배당 등 제외)
                    if quarter is not None and not self._is_actual_quarterly_report(report_nm):
                        skipped_quarterly.append({
                            "report_nm": report_nm,
                            "rcept_dt": rcept_dt[:8] if rcept_dt and len(rcept_dt) >= 8 else rcept_dt or "(없음)",
                            "quarter": quarter,
                            "reason": "report_nm이 분기보고서가 아님(3분기배당 등 제외)",
                        })
                        quarter, detected_reprt_code = None, None

                if quarter is not None:
                    if rcept_dt and len(rcept_dt) >= 8:
                        rcept_date = rcept_dt[:8]
                        quarterly_reports.append({
                            'rcept_no': report.get('rcept_no', ''),
                            'rcept_dt': rcept_date,
                            'reprt_code': detected_reprt_code or '',
                            'report_nm': report_nm,
                            'quarter': quarter,
                        })
                    else:
                        skipped_quarterly.append({
                            'report_nm': report_nm,
                            'rcept_dt': rcept_dt or '(없음)',
                            'quarter': quarter,
                            'reason': 'rcept_dt 길이 부족',
                        })

            quarterly_reports.sort(key=lambda x: x['rcept_dt'], reverse=True)
            result_list = quarterly_reports[:limit]

            self._log_quarterly_reports_debug(
                corp_code, bgn_de, end_date,
                all_reports, result_list, skipped_quarterly,
            )
            return result_list

        except Exception as e:
            logger.warning("분기보고서 목록 조회 실패: %s", e)
            return []

    def get_financial_indicators(self, corp_code, bsns_year, reprt_code='11011', idx_cl_code='M210000'):
        """
        재무지표 조회 (계산된 비율 지표)
        
        이미 계산된 재무 비율/지표를 조회합니다.
        - API: fnlttCmpnyIndx.json (다중회사 주요재무지표)
        - 데이터 형태: 지표 코드(idx_code)와 지표값(idx_val)
        - 예시: {"idx_code": "M211300", "idx_val": "20.5"} → 매출총이익률 20.5%
        
        get_financial_statement()와의 차이:
        - get_financial_statement(): 원시 금액 데이터 (매출액 1000억원, 영업이익 100억원 등)
        - 이 메서드: 계산된 비율 지표 (매출총이익률 20%, ROE 15% 등)
        
        지표분류코드:
        - M210000: 수익성지표 (매출총이익률, ROE, 판관비율, 총자산영업이익률 등)
        - M220000: 안정성지표
        - M230000: 성장성지표
        - M240000: 활동성지표
        
        주요 지표 코드 (수익성지표):
        - M211300: 매출총이익률
        - M211800: 판관비율
        - M212000: 총자산영업이익률
        - M211550: ROE
        
        Args:
            corp_code: 기업 고유번호 (8자리)
            bsns_year: 사업연도 (예: '2024')
            reprt_code: 보고서 코드 ('11011': 사업보고서)
            idx_cl_code: 지표분류코드 (기본값: 'M210000' - 수익성지표)
            
        Returns:
            재무지표 데이터 (list) - 각 항목은 지표 코드와 지표값을 포함
        """
        params = {
            'corp_code': corp_code,
            'bsns_year': bsns_year,
            'reprt_code': reprt_code,
            'idx_cl_code': idx_cl_code
        }
        
        result = self._make_request("fnlttCmpnyIndx.json", params=params)
        
        # 응답 검증
        if isinstance(result, dict) and result.get('status') != '000':
            raise Exception(f"재무지표 조회 실패: {result.get('message', '알 수 없는 오류')}")
        
        # list 필드에서 재무지표 데이터 반환
        return result.get('list', [])
    
    # 향후 필요한 메서드들을 여기에 추가
    # 예: 공시 정보 조회 등

