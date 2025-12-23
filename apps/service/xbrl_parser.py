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


class XbrlParser:
    """XBRL XML 파일 파싱 클래스"""
    
    def __init__(self):
        """XBRL 파서 초기화"""
        self.mappings = self._load_acode_mappings()
    
    def _load_acode_mappings(self):
        """
        ACODE 매핑 테이블 로드
        
        Returns:
            매핑 테이블 딕셔너리
        """
        mappings_path = Path(__file__).parent.parent.parent / 'xbrl_acode_mappings.json'
        with open(mappings_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def extract_annual_report_file(self, zip_data: bytes) -> bytes:
        """
        ZIP 파일에서 사업보고서 XML 파일 추출
        
        Args:
            zip_data: ZIP 파일 바이너리 데이터
            
        Returns:
            사업보고서 XML 파일 바이너리 데이터
        """
        # #region agent log
        import json
        with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"K","location":"xbrl_parser.py:29","message":"extract_annual_report_file entry","data":{"zip_size":len(zip_data)},"timestamp":int(__import__('time').time()*1000)})+'\n')
        # #endregion
        
        with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
            file_list = z.namelist()
            # #region agent log
            with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"K","location":"xbrl_parser.py:42","message":"ZIP file list","data":{"total_files":len(file_list),"xml_files":[f for f in file_list if f.endswith('.xml')]},"timestamp":int(__import__('time').time()*1000)})+'\n')
            # #endregion
            
            # ZIP 파일 내 모든 파일 목록 확인
            for filename in file_list:
                if filename.endswith('.xml'):
                    # XML 파일 읽기
                    xml_content = z.read(filename)
                    
                    # #region agent log
                    with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"K","location":"xbrl_parser.py:50","message":"checking XML file","data":{"filename":filename,"xml_size":len(xml_content)},"timestamp":int(__import__('time').time()*1000)})+'\n')
                    # #endregion
                    
                    # DOCUMENT-NAME ACODE="11011" 확인 (사업보고서)
                    # XML 파싱 전에 문자열 검색으로 먼저 확인 (더 빠르고 안전)
                    xml_str = xml_content.decode('utf-8', errors='ignore')
                    
                    # #region agent log
                    with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                        has_doc_name = 'DOCUMENT-NAME' in xml_str and 'ACODE="11011"' in xml_str
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"L","location":"xbrl_parser.py:58","message":"string search for DOCUMENT-NAME","data":{"filename":filename,"has_doc_name":has_doc_name},"timestamp":int(__import__('time').time()*1000)})+'\n')
                    # #endregion
                    
                    # 문자열 검색으로 DOCUMENT-NAME ACODE="11011" 확인
                    if 'DOCUMENT-NAME' in xml_str and 'ACODE="11011"' in xml_str:
                        # XML 파싱 시도 (파싱 실패해도 문자열 검색으로 찾았으므로 반환)
                        try:
                            # 기본 파서로 시도
                            root = ET.fromstring(xml_content)
                            
                            # 여러 방법으로 DOCUMENT-NAME 찾기 시도
                            doc_name = root.find('.//DOCUMENT-NAME[@ACODE="11011"]')
                            if doc_name is None:
                                # 직접 자식 요소로 찾기
                                doc_name = root.find('DOCUMENT-NAME[@ACODE="11011"]')
                            if doc_name is None:
                                # 모든 DOCUMENT-NAME 찾아서 ACODE 확인
                                for elem in root.iter('DOCUMENT-NAME'):
                                    if elem.get('ACODE') == '11011':
                                        doc_name = elem
                                        break
                            
                            # #region agent log
                            with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"L","location":"xbrl_parser.py:75","message":"XML parsed successfully","data":{"filename":filename,"root_tag":root.tag,"doc_name_found":doc_name is not None},"timestamp":int(__import__('time').time()*1000)})+'\n')
                            # #endregion
                            
                            if doc_name is not None:
                                # #region agent log
                                with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"L","location":"xbrl_parser.py:80","message":"annual report found via XML parsing","data":{"filename":filename},"timestamp":int(__import__('time').time()*1000)})+'\n')
                                # #endregion
                                return xml_content
                        except (ET.ParseError, ExpatError, UnicodeDecodeError) as e:
                            # 파싱 실패해도 문자열 검색으로 찾았으므로 반환
                            # #region agent log
                            with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"L","location":"xbrl_parser.py:88","message":"XML parse failed but string search found DOCUMENT-NAME, returning anyway","data":{"filename":filename,"error":str(e)},"timestamp":int(__import__('time').time()*1000)})+'\n')
                            # #endregion
                            return xml_content
                        except Exception as e:
                            # 파싱 실패해도 문자열 검색으로 찾았으므로 반환
                            # #region agent log
                            with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"L","location":"xbrl_parser.py:93","message":"unexpected error but string search found, returning anyway","data":{"filename":filename,"error":str(e),"error_type":type(e).__name__},"timestamp":int(__import__('time').time()*1000)})+'\n')
                            # #endregion
                            return xml_content
                    else:
                        # #region agent log
                        with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"L","location":"xbrl_parser.py:97","message":"DOCUMENT-NAME not found in string search","data":{"filename":filename},"timestamp":int(__import__('time').time()*1000)})+'\n')
                        # #endregion
                        continue
        
        # #region agent log
        with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"K","location":"xbrl_parser.py:90","message":"annual report not found","data":{},"timestamp":int(__import__('time').time()*1000)})+'\n')
        # #endregion
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
        
        # 연간만 채택 (dFY = duration Fiscal Year, 분기 제외)
        if 'dFY' not in context_ref:
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
        정규식을 사용하여 ACODE 인덱스 생성 (XML 파싱 실패 시 대체 방법)
        
        Args:
            xml_str: XML 문자열
            
        Returns:
            ACODE를 키로 하는 딕셔너리
        """
        acode_index = {}
        
        # #region agent log
        import json
        with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"O","location":"xbrl_parser.py:218","message":"regex parsing started","data":{"xml_str_length":len(xml_str)},"timestamp":int(__import__('time').time()*1000)})+'\n')
        # #endregion
        
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
            
            if acode not in acode_index:
                acode_index[acode] = []
            
            acode_index[acode].append({
                'value': value_str,
                'context': acontext,
                'adecimal': adecimal
            })
        
        # #region agent log
        with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"O","location":"xbrl_parser.py:270","message":"regex parsing completed","data":{"te_tags_found":te_count,"matched_after_filter":matched_count,"acode_index_size":len(acode_index)},"timestamp":int(__import__('time').time()*1000)})+'\n')
        # #endregion
        
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
            acode_index: build_acode_index()로 생성한 인덱스
            indicator_key: 지표 키 (예: "tangible_asset_acquisition")
            
        Returns:
            추출된 값 (정수, 없으면 0)
        """
        if indicator_key not in self.mappings:
            return 0
        
        mapping = self.mappings[indicator_key]
        primary_acode = mapping.get('primary_acode', '')
        candidate_acodes = mapping.get('candidate_acodes', [])
        
        # primary_acode와 candidate_acodes를 합쳐서 시도
        all_acodes = [primary_acode] + candidate_acodes
        
        # 콜론(:)을 언더스코어(_)로 변환한 버전도 시도
        normalized_acodes = []
        for acode in all_acodes:
            normalized_acodes.append(acode)
            if ':' in acode:
                normalized_acodes.append(acode.replace(':', '_'))
        
        # 각 ACODE 시도
        for acode in normalized_acodes:
            if acode in acode_index:
                entries = acode_index[acode]
                if entries:
                    # 첫 번째 항목 사용 (당기 데이터)
                    entry = entries[0]
                    return self._normalize_decimal(entry['value'], entry['adecimal'])
        
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
        # #region agent log
        import json
        with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"M","location":"xbrl_parser.py:228","message":"parse_xbrl_file entry","data":{"xml_size":len(xml_content)},"timestamp":int(__import__('time').time()*1000)})+'\n')
        # #endregion
        
        try:
            # #region agent log
            with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"M","location":"xbrl_parser.py:235","message":"attempting XML parse","data":{},"timestamp":int(__import__('time').time()*1000)})+'\n')
            # #endregion
            
            # XML 파싱 시도 - 여러 방법 시도
            root = None
            try:
                root = ET.fromstring(xml_content)
            except ET.ParseError as e1:
                # #region agent log
                with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"M","location":"xbrl_parser.py:343","message":"ET.fromstring failed, trying incremental parser","data":{"error":str(e1)},"timestamp":int(__import__('time').time()*1000)})+'\n')
                # #endregion
                # Incremental parser 시도
                try:
                    parser = ET.XMLParser()
                    parser.feed(xml_content)
                    root = parser.close()
                except Exception as e2:
                    # #region agent log
                    with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"M","location":"xbrl_parser.py:351","message":"incremental parser also failed, trying regex","data":{"error":str(e2)},"timestamp":int(__import__('time').time()*1000)})+'\n')
                    # #endregion
                    # XML 파싱 실패 시 정규식으로 대체
                    xml_str = xml_content.decode('utf-8', errors='ignore')
                    # #region agent log
                    with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"N","location":"xbrl_parser.py:356","message":"building acode index from regex","data":{},"timestamp":int(__import__('time').time()*1000)})+'\n')
                    # #endregion
                    acode_index = self.build_acode_index_from_regex(xml_str)
                    # #region agent log
                    with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"N","location":"xbrl_parser.py:360","message":"acode index built from regex","data":{"acode_count":len(acode_index)},"timestamp":int(__import__('time').time()*1000)})+'\n')
                    # #endregion
                    
                    # 각 지표 추출
                    result = {}
                    for indicator_key in self.mappings.keys():
                        value = self.extract_value_by_acode(acode_index, indicator_key)
                        result[indicator_key] = value
                        # #region agent log
                        with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"N","location":"xbrl_parser.py:370","message":"extracted indicator from regex","data":{"indicator_key":indicator_key,"value":value},"timestamp":int(__import__('time').time()*1000)})+'\n')
                        # #endregion
                    
                    # #region agent log
                    with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"N","location":"xbrl_parser.py:375","message":"parse_xbrl_file completed using regex","data":{"result_keys":list(result.keys())},"timestamp":int(__import__('time').time()*1000)})+'\n')
                    # #endregion
                    return result
            
            if root is None:
                raise ValueError("XML 파싱 실패: root가 None입니다")
            
            # #region agent log
            with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"M","location":"xbrl_parser.py:382","message":"XML parsed successfully","data":{"root_tag":root.tag},"timestamp":int(__import__('time').time()*1000)})+'\n')
            # #endregion
            
            # ACODE 인덱스 생성
            # #region agent log
            with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"M","location":"xbrl_parser.py:387","message":"building acode index","data":{},"timestamp":int(__import__('time').time()*1000)})+'\n')
            # #endregion
            acode_index = self.build_acode_index(root)
            
            # #region agent log
            with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"M","location":"xbrl_parser.py:267","message":"acode index built","data":{"acode_count":len(acode_index)},"timestamp":int(__import__('time').time()*1000)})+'\n')
            # #endregion
            
            # 각 지표 추출
            result = {}
            for indicator_key in self.mappings.keys():
                value = self.extract_value_by_acode(acode_index, indicator_key)
                result[indicator_key] = value
                # #region agent log
                with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"M","location":"xbrl_parser.py:275","message":"extracted indicator","data":{"indicator_key":indicator_key,"value":value},"timestamp":int(__import__('time').time()*1000)})+'\n')
                # #endregion
            
            # #region agent log
            with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"M","location":"xbrl_parser.py:279","message":"parse_xbrl_file completed","data":{"result_keys":list(result.keys())},"timestamp":int(__import__('time').time()*1000)})+'\n')
            # #endregion
            return result
        except ET.ParseError as e:
            # #region agent log
            with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"M","location":"xbrl_parser.py:283","message":"parse_xbrl_file failed with ParseError","data":{"error":str(e)},"timestamp":int(__import__('time').time()*1000)})+'\n')
            # #endregion
            raise ValueError(f"XML 파싱 실패: {e}")
        except Exception as e:
            # #region agent log
            with open(r'c:\Long_Term_Investing\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"M","location":"xbrl_parser.py:288","message":"parse_xbrl_file failed with unexpected error","data":{"error":str(e),"error_type":type(e).__name__},"timestamp":int(__import__('time').time()*1000)})+'\n')
            # #endregion
            raise

