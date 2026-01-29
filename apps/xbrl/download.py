"""
XBRL 파일 다운로드 (DART document.xml API)

격리: DART client에 두지 않고 xbrl 폴더에서 직접 호출.
"""
import requests
from django.conf import settings
from pathlib import Path

BASE_URL = "https://opendart.fss.or.kr/api"


def download_xbrl(rcept_no: str, save_path: str | Path | None = None) -> bytes | str:
    """
    XBRL 파일 다운로드 (DART document.xml API)

    Args:
        rcept_no: 접수번호 (14자리)
        save_path: 저장 경로 (None이면 바이너리 반환)

    Returns:
        save_path 있으면 저장 경로(str), 없으면 바이너리(bytes)
    """
    api_key = getattr(settings, "DART_API_KEY", "") or ""
    if not api_key:
        raise ValueError("DART_API_KEY가 설정되지 않았습니다. .env를 확인하세요.")

    url = f"{BASE_URL}/document.xml"
    params = {"rcept_no": rcept_no, "crtfc_key": api_key}
    timeout = 30
    if hasattr(settings, "DATA_COLLECTION") and isinstance(settings.DATA_COLLECTION, dict):
        timeout = settings.DATA_COLLECTION.get("API_TIMEOUT", 30)

    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.content

    if save_path is not None:
        path = Path(save_path)
        path.write_bytes(data)
        return str(path)
    return data
