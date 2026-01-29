"""
기업번호(corp_code) / 종목코드(stock_code) 변환 (DartClient 사용)
"""
from apps.dart.client import DartClient


def resolve_corp_code(corp_code: str) -> tuple[str | None, str | None]:
    """
    종목코드(6자리) → 기업번호(8자리) 변환. 8자리면 그대로 반환.

    Returns:
        (resolved_corp_code, error_message)
        - 성공: (corp_code, None)
        - 6자리인데 변환 실패: (None, "종목코드 {corp_code}에 해당하는 기업번호를 찾을 수 없습니다.")
    """
    if not (len(corp_code) == 6 and corp_code.isdigit()):
        return (corp_code, None)
    client = DartClient()
    converted = client._get_corp_code_by_stock_code(corp_code)
    if not converted:
        return (None, f"종목코드 {corp_code}에 해당하는 기업번호를 찾을 수 없습니다.")
    return (converted, None)


def get_stock_code_by_corp_code(corp_code: str) -> str | None:
    """
    기업번호(corp_code)를 종목코드(stock_code)로 변환

    DartClient의 _corp_code_mapping_cache를 역방향으로 검색하여 변환합니다.
    캐시가 비어있으면 먼저 로드합니다.

    Args:
        corp_code: 기업번호 (8자리, 예: '00126380')

    Returns:
        종목코드 (6자리, 예: '005930') 또는 None (찾을 수 없는 경우)
    """
    dart_client = DartClient()

    if not dart_client._corp_code_mapping_cache:
        dart_client.load_corp_code_xml()

    for stock_code, cached_corp_code in dart_client._corp_code_mapping_cache.items():
        if cached_corp_code == corp_code:
            return stock_code

    return None
