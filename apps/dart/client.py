"""
DART OpenDART API 클라이언트
"""
import time
import requests
import zipfile
import io
import xml.etree.ElementTree as ET
from django.conf import settings


class DartClient:
    """DART OpenDART API 클라이언트"""
    
    BASE_URL = "https://opendart.fss.or.kr/api"
    
    # 종목코드 → corp_code 매핑 캐시 (클래스 변수)
    _corp_code_mapping_cache = {}
    
    def __init__(self, api_key=None):
        """
        DART 클라이언트 초기화
        
        Args:
            api_key: DART API 키 (없으면 settings에서 가져옴)
        """
        self.api_key = api_key or settings.DART_API_KEY
        if not self.api_key:
            raise ValueError("DART_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    
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
        
        last_exception = None
        
        for attempt in range(max_retries + 1):  # 0, 1, 2, 3 (총 4번 시도)
            try:
                response = requests.get(url, params=params, timeout=timeout)
                
                # 성공한 경우
                if response.status_code == 200:
                    if return_binary:
                        return response.content
                    return response.json()
                
                # 재시도 가능한 오류인지 확인
                if response.status_code in retryable_status_codes:
                    if attempt < max_retries:  # 마지막 시도가 아니면 재시도
                        # Rate Limit (429)인 경우 Retry-After 헤더 확인
                        if response.status_code == 429:
                            retry_after = response.headers.get('Retry-After')
                            if retry_after:
                                try:
                                    wait_time = int(retry_after)
                                except ValueError:
                                    wait_time = 2 ** attempt  # Retry-After가 유효하지 않으면 exponential backoff
                            else:
                                wait_time = 2 ** attempt
                        else:
                            # Exponential Backoff: 2^attempt 초 대기 (1초, 2초, 4초...)
                            wait_time = 2 ** attempt
                        
                        time.sleep(wait_time)
                        continue  # 재시도
                    else:
                        # 마지막 시도에서도 실패
                        response.raise_for_status()
                else:
                    # 재시도 불가능한 오류 (400, 401, 404 등)
                    response.raise_for_status()
                    
            except requests.exceptions.Timeout as e:
                # 타임아웃은 재시도 가능
                last_exception = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(f"DART API 요청 실패 (타임아웃, 최대 {max_retries}회 재시도 후 실패): {str(e)}")
                    
            except requests.exceptions.ConnectionError as e:
                # 네트워크 연결 오류는 재시도 가능
                last_exception = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(f"DART API 요청 실패 (연결 오류, 최대 {max_retries}회 재시도 후 실패): {str(e)}")
                    
            except requests.exceptions.HTTPError as e:
                # HTTP 오류 (이미 위에서 상태 코드로 처리했지만 안전장치)
                last_exception = e
                if attempt < max_retries and hasattr(e.response, 'status_code') and e.response.status_code in retryable_status_codes:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
                raise  # 재시도 불가능한 오류는 즉시 raise
                
            except requests.exceptions.RequestException as e:
                # 기타 RequestException
                last_exception = e
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(f"DART API 요청 실패 (최대 {max_retries}회 재시도 후 실패): {str(e)}")
        
        # 모든 재시도 실패 (이 코드는 실행되지 않아야 하지만 안전장치)
        raise Exception(f"DART API 요청 실패 (최대 {max_retries}회 재시도 후 실패): {str(last_exception)}")
    
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
            # 기업 고유번호 XML 파일 다운로드
            url = f"{self.BASE_URL}/corpCode.xml"
            params = {'crtfc_key': self.api_key}
            timeout = settings.DATA_COLLECTION['API_TIMEOUT']
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            
            # ZIP 파일 압축 해제
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
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
            raise Exception(f"재무제표 조회 실패: {result.get('message', '알 수 없는 오류')}")
        
        # list 필드에서 재무제표 데이터 반환
        return result.get('list', [])
    
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
    
    def download_xbrl(self, rcept_no, save_path=None):
        """
        XBRL 파일 다운로드
        
        Args:
            rcept_no: 접수번호 (14자리)
            save_path: 저장 경로 (None이면 바이너리 데이터 반환)
            
        Returns:
            저장 경로 또는 바이너리 데이터
        """
        params = {
            'rcept_no': rcept_no
        }
        
        # XBRL 파일은 ZIP 형식으로 다운로드됨
        binary_data = self._make_request("document.xml", params=params, return_binary=True)
        
        if save_path:
            with open(save_path, 'wb') as f:
                f.write(binary_data)
            return save_path
        else:
            return binary_data
    
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
            print(f"경고: {year}년 사업보고서 접수번호 조회 실패: {e}")
            print(f"  에러 타입: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            return None
    
    def download_xbrl_and_extract_annual_report(self, rcept_no: str) -> bytes:
        """
        XBRL 파일 다운로드 및 사업보고서 XML 추출
        
        Args:
            rcept_no: 접수번호 (14자리)
            
        Returns:
            사업보고서 XML 파일 바이너리 데이터
        """
        from apps.service.xbrl_parser import XbrlParser
        
        # ZIP 파일 다운로드
        zip_data = self.download_xbrl(rcept_no)
        
        # 사업보고서 XML 추출
        parser = XbrlParser()
        xml_content = parser.extract_annual_report_file(zip_data)
        
        return xml_content
    
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

