"""
XBRL 파일 파서
"""
import zipfile
import io
import xml.etree.ElementTree as ET
from xml.parsers.expat import ExpatError
from pathlib import Path
import json
import re
from apps.utils.utils import normalize_acode


class XbrlParser:
    """XBRL XML 파일 파싱 클래스"""
    
    def __init__(self):
        """XBRL 파서 초기화"""
        self.mappings = self._load_acode_mappings()
        self._normalized_mappings = self._preprocess_mappings()
    
    def _load_acode_mappings(self):
        """
        ACODE 매핑 테이블 로드
        
        Returns:
            매핑 테이블 딕셔너리
        """
        mappings_path = Path(__file__).parent.parent.parent / 'xbrl_acode_mappings.json'
        with open(mappings_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _preprocess_mappings(self):
        """
        매핑 테이블 사전 처리: 후보 ACODE들을 정규화해서 저장
        
        Returns:
            정규화된 매핑 딕셔너리 {indicator_key: [normalized_acode1, normalized_acode2, ...]}
        """
        normalized = {}
        for indicator_key, mapping in self.mappings.items():
            primary_acode = mapping.get('primary_acode', '')
            candidate_acodes = mapping.get('candidate_acodes', [])
            
            # primary_acode와 candidate_acodes를 합쳐서 정규화
            all_acodes = [primary_acode] + candidate_acodes
            
            # 정규화 함수를 사용하여 모든 ACODE 정규화
            normalized_acodes = []
            for acode in all_acodes:
                if acode:
                    # 콜론이 있는 경우 원본(콜론 포함)과 변환된 버전(언더스코어) 둘 다 생성
                    if ':' in acode:
                        # 원본 정규화 (콜론 유지, 소문자만 변환)
                        normalized_with_colon = acode.lower()
                        if normalized_with_colon not in normalized_acodes:
                            normalized_acodes.append(normalized_with_colon)
                        
                        # 콜론을 언더스코어로 변환한 버전도 생성
                        normalized_with_underscore = normalize_acode(acode)
                        if normalized_with_underscore not in normalized_acodes:
                            normalized_acodes.append(normalized_with_underscore)
                    else:
                        # 콜론이 없으면 정규화만
                        normalized_acode = normalize_acode(acode)
                        if normalized_acode not in normalized_acodes:
                            normalized_acodes.append(normalized_acode)
            
            normalized[indicator_key] = normalized_acodes
        
        return normalized
    
    def extract_annual_report_file(self, zip_data: bytes) -> bytes:
        """
        ZIP 파일에서 사업보고서 XML 파일 추출
        
        Args:
            zip_data: ZIP 파일 바이너리 데이터
            
        Returns:
            사업보고서 XML 파일 바이너리 데이터
        """
        
        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            file_list = z.namelist()
            
            # ZIP 파일 내 모든 파일 목록 확인
            for filename in file_list:
                if filename.endswith('.xml'):
                    # XML 파일 읽기
                    xml_content = z.read(filename)
                    
                    # DOCUMENT-NAME ACODE="11011" 확인 (사업보고서)
                    # 문자열 검색으로 확인 (더 빠르고 안전)
                    xml_str = xml_content.decode('utf-8', errors='ignore')
                    
                    # 문자열 검색으로 DOCUMENT-NAME ACODE="11011" 확인
                    if 'DOCUMENT-NAME' in xml_str and 'ACODE="11011"' in xml_str:
                        # 사업보고서 파일이므로 바로 반환
                        return xml_content
        
        raise ValueError("ZIP 파일에서 사업보고서 XML을 찾을 수 없습니다.")
    
    def _normalize_decimal(self, value: str, adecimal: str) -> int:
        """
        ADECIMAL 값을 기반으로 실제 금액 계산 (XBRL 전용)
        
        Args:
            value: 금액 문자열 (쉼표 포함 가능, 음수는 괄호 표기)
            adecimal: ADECIMAL 속성 값 (예: "-6")
            
        Returns:
            정규화된 금액 (정수)
        """
        if not value or value.strip() == '':
            return 0
        
        # 괄호 제거 (음수 처리)
        is_negative = value.strip().startswith('(') and value.strip().endswith(')')
        if is_negative:
            value = value.strip()[1:-1]  # 괄호 제거
        
        # 쉼표 제거
        value = value.replace(',', '').strip()
        
        try:
            num_value = float(value)
        except ValueError:
            return 0
        
        # ADECIMAL 기반 단위 변환
        # ADECIMAL="-6" → 백만원 단위 → 1,000,000 곱하기
        try:
            decimal_power = int(adecimal)
            multiplier = 10 ** abs(decimal_power)
            result = int(num_value * multiplier)
        except (ValueError, TypeError):
            # ADECIMAL 파싱 실패 시 원본 값 사용
            result = int(num_value)
        
        if is_negative:
            result = -result
        
        return result
    
    def filter_context(self, context_ref: str) -> bool:
        """
        contextRef 필터링 - 당기 연간 연결재무제표만 채택
        
        Args:
            context_ref: ACONTEXT 속성 값
            
        Returns:
            True면 채택, False면 제외
        """
        if not context_ref:
            return False
        
        # 당기 연간만 채택 (CFY = Current Fiscal Year)
        if 'CFY' not in context_ref:
            return False
        
        # 연간만 채택
        # - dFY (duration Fiscal Year): 현금흐름표, 손익계산서용 (기간)
        # - eFY (ending Fiscal Year): 재무상태표용 (시점)
        if 'dFY' not in context_ref and 'eFY' not in context_ref:
            return False
        
        # 연결재무제표 우선 (ConsolidatedMember)
        if 'ConsolidatedMember' in context_ref:
            return True
        
        # 연결이 없으면 별도도 허용
        if 'SeparateMember' in context_ref:
            return True
        
        return False
    
    def build_acode_index_from_regex(self, xml_str: str) -> dict:
        """
        정규식을 사용하여 ACODE 인덱스 생성
        
        Args:
            xml_str: XML 문자열
            
        Returns:
            ACODE를 키로 하는 딕셔너리
        """
        acode_index = {}
        
        # TE 태그를 정규식으로 찾기 (속성 순서가 다를 수 있으므로 각각 찾기)
        # <TE ... ACODE="..." ... ACONTEXT="..." ... ADECIMAL="...">...값...</TE>
        # P 태그가 있으면 P 태그 안의 값, 없으면 TE 태그 안의 직접 텍스트
        te_pattern = r'<TE([^>]*)>(.*?)</TE>'
        
        te_count = 0
        matched_count = 0
        for match in re.finditer(te_pattern, xml_str, re.DOTALL):
            te_count += 1
            attrs_str = match.group(1)
            content = match.group(2)
            
            # ACODE 추출
            acode_match = re.search(r'ACODE="([^"]+)"', attrs_str)
            if not acode_match:
                continue
            acode = acode_match.group(1)
            
            # ACODE 정규화 (매핑 테이블과 비교를 위해)
            normalized_acode = normalize_acode(acode)
            
            # ACONTEXT 추출
            acontext_match = re.search(r'ACONTEXT="([^"]*)"', attrs_str)
            acontext = acontext_match.group(1) if acontext_match else ''
            
            # ADECIMAL 추출
            adecimal_match = re.search(r'ADECIMAL="([^"]*)"', attrs_str)
            adecimal = adecimal_match.group(1) if adecimal_match else '-6'
            
            # 필터링: 당기 연간만
            if not self.filter_context(acontext):
                continue
            
            matched_count += 1
            
            # 값 추출: P 태그가 있으면 P 태그 안의 값, 없으면 직접 텍스트
            p_match = re.search(r'<P[^>]*>([^<]+)</P>', content)
            if p_match:
                value_str = p_match.group(1).strip()
            else:
                # P 태그가 없으면 직접 텍스트 (태그 제거)
                value_str = re.sub(r'<[^>]+>', '', content).strip()
            
            if not value_str or value_str == '-':
                continue
            
            # 정규화된 ACODE를 키로 사용 (대소문자 차이 해결)
            if normalized_acode not in acode_index:
                acode_index[normalized_acode] = []
            
            acode_index[normalized_acode].append({
                'value': value_str,
                'context': acontext,
                'adecimal': adecimal
            })
        
        return acode_index
    
    def build_acode_index(self, xml_root) -> dict:
        """
        ACODE → 값 인덱스 생성
        
        Args:
            xml_root: XML 루트 엘리먼트
            
        Returns:
            ACODE를 키로 하는 딕셔너리
            {
                "ifrs-full_PurchaseOfPropertyPlantAndEquipment": [
                    {
                        "value": "51406",
                        "context": "CFY2024dFY_...",
                        "adecimal": "-6"
                    },
                    ...
                ]
            }
        """
        acode_index = {}
        
        # 모든 TE 태그 찾기 (ACODE 속성이 있는 것만)
        for te in xml_root.iter('TE'):
            acode = te.get('ACODE')
            if not acode:
                continue
            
            # ACONTEXT 확인
            acontext = te.get('ACONTEXT', '')
            
            # 필터링: 당기 연간만
            if not self.filter_context(acontext):
                continue
            
            # 값 추출 (P 태그 내부)
            p_tag = te.find('P')
            if p_tag is None or p_tag.text is None:
                continue
            
            value_str = p_tag.text.strip()
            if not value_str or value_str == '-':
                continue
            
            # ADECIMAL 추출
            adecimal = te.get('ADECIMAL', '-6')  # 기본값: -6 (백만원)
            
            # ACODE별로 리스트에 추가
            if acode not in acode_index:
                acode_index[acode] = []
            
            acode_index[acode].append({
                'value': value_str,
                'context': acontext,
                'adecimal': adecimal
            })
        
        return acode_index
    
    def extract_value_by_acode(self, acode_index: dict, indicator_key: str) -> int:
        """
        특정 지표의 ACODE로 값 추출
        
        Args:
            acode_index: build_acode_index_from_regex()로 생성한 인덱스
            indicator_key: 지표 키 (예: "tangible_asset_acquisition")
            
        Returns:
            추출된 값 (정수, 없으면 0)
        """
        if indicator_key not in self._normalized_mappings:
            return 0
        
        # 이미 정규화된 후보 ACODE 리스트 사용 (사전 처리됨)
        normalized_acodes = self._normalized_mappings[indicator_key]
        
        # 각 ACODE 시도 (O(1) 조회)
        for acode in normalized_acodes:
            if acode in acode_index:
                entries = acode_index[acode]
                if entries:
                    # 첫 번째 항목 사용 (당기 데이터)
                    entry = entries[0]
                    value = self._normalize_decimal(entry['value'], entry['adecimal'])
                    return value
        
        return 0
    
    def parse_xbrl_file(self, xml_content: bytes) -> dict:
        """
        XBRL XML 파일 파싱
        
        Args:
            xml_content: XML 파일 바이너리 데이터
            
        Returns:
            추출된 지표 딕셔너리
            {
                "tangible_asset_acquisition": 51406355000000,
                "intangible_asset_acquisition": 1234567890000,
                "cfo": 72982621000000
            }
        """
        # 정규식을 사용하여 ACODE 인덱스 생성
        xml_str = xml_content.decode('utf-8', errors='ignore')
        acode_index = self.build_acode_index_from_regex(xml_str)
        
        # 각 지표 추출
        result = {}
        for indicator_key in self.mappings.keys():
            value = self.extract_value_by_acode(acode_index, indicator_key)
            result[indicator_key] = value
        
        return result

