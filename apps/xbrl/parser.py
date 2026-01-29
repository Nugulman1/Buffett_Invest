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

from apps.xbrl.acode_utils import normalize_acode


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
        mappings_path = Path(__file__).parent / "xbrl_acode_mappings.json"
        with open(mappings_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _preprocess_mappings(self):
        """
        매핑 테이블 사전 처리: 후보 ACODE들을 정규화해서 저장

        Returns:
            정규화된 매핑 딕셔너리 {indicator_key: [normalized_acode1, normalized_acode2, ...]}
        """
        normalized = {}
        for indicator_key, mapping in self.mappings.items():
            primary_acode = mapping.get("primary_acode", "")
            candidate_acodes = mapping.get("candidate_acodes", [])

            all_acodes = [primary_acode] + candidate_acodes
            normalized_acodes = []
            for acode in all_acodes:
                if acode:
                    if ":" in acode:
                        normalized_with_colon = acode.lower()
                        if normalized_with_colon not in normalized_acodes:
                            normalized_acodes.append(normalized_with_colon)
                        normalized_with_underscore = normalize_acode(acode)
                        if normalized_with_underscore not in normalized_acodes:
                            normalized_acodes.append(normalized_with_underscore)
                    else:
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

            for filename in file_list:
                if filename.endswith(".xml"):
                    xml_content = z.read(filename)
                    xml_str = xml_content.decode("utf-8", errors="ignore")
                    if "DOCUMENT-NAME" in xml_str and 'ACODE="11011"' in xml_str:
                        return xml_content

        raise ValueError("ZIP 파일에서 사업보고서 XML을 찾을 수 없습니다.")

    def _normalize_decimal(self, value: str, adecimal: str) -> int:
        """
        ADECIMAL 값을 기반으로 실제 금액 계산 (XBRL 전용)
        """
        if not value or value.strip() == "":
            return 0

        is_negative = value.strip().startswith("(") and value.strip().endswith(")")
        if is_negative:
            value = value.strip()[1:-1]

        value = value.replace(",", "").strip()

        try:
            num_value = float(value)
        except ValueError:
            return 0

        try:
            decimal_power = int(adecimal)
            multiplier = 10 ** abs(decimal_power)
            result = int(num_value * multiplier)
        except (ValueError, TypeError):
            result = int(num_value)

        if is_negative:
            result = -result

        return result

    def filter_context(self, context_ref: str) -> bool:
        """contextRef 필터링 - 당기 연간 연결재무제표만 채택"""
        if not context_ref:
            return False
        if "CFY" not in context_ref:
            return False
        if "dFY" not in context_ref and "eFY" not in context_ref:
            return False
        if "ConsolidatedMember" in context_ref:
            return True
        if "SeparateMember" in context_ref:
            return True
        return False

    def build_acode_index_from_regex(self, xml_str: str) -> dict:
        """정규식으로 ACODE 인덱스 생성"""
        acode_index = {}
        te_pattern = r"<TE([^>]*)>(.*?)</TE>"

        for match in re.finditer(te_pattern, xml_str, re.DOTALL):
            attrs_str = match.group(1)
            content = match.group(2)

            acode_match = re.search(r'ACODE="([^"]+)"', attrs_str)
            if not acode_match:
                continue
            acode = acode_match.group(1)
            normalized_acode = normalize_acode(acode)

            acontext_match = re.search(r'ACONTEXT="([^"]*)"', attrs_str)
            acontext = acontext_match.group(1) if acontext_match else ""

            adecimal_match = re.search(r'ADECIMAL="([^"]*)"', attrs_str)
            adecimal = adecimal_match.group(1) if adecimal_match else "-6"

            if not self.filter_context(acontext):
                continue

            p_match = re.search(r"<P[^>]*>([^<]+)</P>", content)
            if p_match:
                value_str = p_match.group(1).strip()
            else:
                value_str = re.sub(r"<[^>]+>", "", content).strip()

            if not value_str or value_str == "-":
                continue

            if normalized_acode not in acode_index:
                acode_index[normalized_acode] = []

            acode_index[normalized_acode].append(
                {"value": value_str, "context": acontext, "adecimal": adecimal}
            )

        return acode_index

    def build_acode_index(self, xml_root) -> dict:
        """ACODE → 값 인덱스 생성 (ElementTree용)"""
        acode_index = {}
        for te in xml_root.iter("TE"):
            acode = te.get("ACODE")
            if not acode:
                continue
            acontext = te.get("ACONTEXT", "")
            if not self.filter_context(acontext):
                continue
            p_tag = te.find("P")
            if p_tag is None or p_tag.text is None:
                continue
            value_str = p_tag.text.strip()
            if not value_str or value_str == "-":
                continue
            adecimal = te.get("ADECIMAL", "-6")
            if acode not in acode_index:
                acode_index[acode] = []
            acode_index[acode].append(
                {"value": value_str, "context": acontext, "adecimal": adecimal}
            )
        return acode_index

    def extract_value_by_acode(self, acode_index: dict, indicator_key: str) -> int:
        """지표 키로 ACODE 인덱스에서 값 추출"""
        if indicator_key not in self._normalized_mappings:
            return 0
        normalized_acodes = self._normalized_mappings[indicator_key]
        for acode in normalized_acodes:
            if acode in acode_index:
                entries = acode_index[acode]
                if entries:
                    entry = entries[0]
                    return self._normalize_decimal(entry["value"], entry["adecimal"])
        return 0

    def parse_xbrl_file(self, xml_content: bytes) -> dict:
        """XBRL XML 파싱 후 지표 딕셔너리 반환"""
        xml_str = xml_content.decode("utf-8", errors="ignore")
        acode_index = self.build_acode_index_from_regex(xml_str)
        result = {}
        for indicator_key in self.mappings.keys():
            result[indicator_key] = self.extract_value_by_acode(
                acode_index, indicator_key
            )
        return result
