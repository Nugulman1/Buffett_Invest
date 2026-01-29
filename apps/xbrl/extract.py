"""
XBRL ZIP에서 사업보고서 XML 추출
"""
from .download import download_xbrl
from .parser import XbrlParser


def extract_annual_report_from_xbrl(rcept_no: str) -> bytes:
    """
    XBRL 다운로드 후 사업보고서 XML 추출

    Args:
        rcept_no: 접수번호 (14자리)

    Returns:
        사업보고서 XML 바이너리
    """
    zip_data = download_xbrl(rcept_no)
    parser = XbrlParser()
    return parser.extract_annual_report_file(zip_data)
