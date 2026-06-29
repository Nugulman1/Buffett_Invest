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


def _stock_code_sort_key(stock_code: str) -> tuple[int, str]:
    """역인덱스 충돌(한 corp에 복수 종목코드) 시 결정적 선택용 정렬키.

    보통주(끝자리 '0') 우선, 동급이면 사전순 최소. (보통주+우선주 합산이 아니라
    대표 1개를 결정적으로 고르는 규칙 — 합산은 시총 이중계상 위험으로 배제.)
    """
    is_not_common = 0 if stock_code.endswith("0") else 1
    return (is_not_common, stock_code)


def build_corp_to_stock_index(forward: dict) -> dict:
    """정방향 {종목코드: corp_code}를 역방향 {corp_code: 대표 종목코드}로 1회 구성.

    한 corp_code에 복수 종목코드가 묶이면 _stock_code_sort_key로 결정적 선택
    (보통주 우선·동급 사전순 최소). dict 삽입순서와 무관하게 같은 결과를 보장한다.
    """
    reverse: dict[str, str] = {}
    for stock_code, corp_code in forward.items():
        existing = reverse.get(corp_code)
        if existing is None or _stock_code_sort_key(stock_code) < _stock_code_sort_key(existing):
            reverse[corp_code] = stock_code
    return reverse


# 역인덱스 캐시: (정방향 dict의 id, len, 역인덱스). 정방향 캐시가 교체되면 id가,
# 더 채워지면 len이 바뀌어 자동 무효화된다. len을 키에 넣는 이유: 멀티스레드 콜드
# 캐시에서 한 스레드가 load_corp_code_xml로 정방향 dict를 in-place로 채우는 도중
# 다른 스레드가 '부분 로드된' dict로 역인덱스를 만들어 캐시해도, 로드가 끝나 len이
# 늘면 다음 호출에서 재빌드돼 부분 결과가 동결되지 않는다(기존 선형스캔의 자가치유 유지).
# 운영에선 load 완료 후 len 고정이라 1회만 구축, 테스트에선 새 dict마다 재구축된다.
_reverse_index_cache: tuple[int, int, dict] | None = None


def get_stock_code_by_corp_code(corp_code: str) -> str | None:
    """
    기업번호(corp_code)를 종목코드(stock_code)로 변환

    DartClient의 _corp_code_mapping_cache(정방향)를 역인덱스로 1회 구축·캐시해
    O(1) 조회한다. 한 corp에 복수 종목코드면 보통주 우선으로 대표 1개를 결정적 선택.

    Args:
        corp_code: 기업번호 (8자리, 예: '00126380')

    Returns:
        종목코드 (6자리, 예: '005930') 또는 None (찾을 수 없는 경우)
    """
    global _reverse_index_cache

    dart_client = DartClient()
    if not dart_client._corp_code_mapping_cache:
        dart_client.load_corp_code_xml()

    forward = dart_client._corp_code_mapping_cache
    if (_reverse_index_cache is None
            or _reverse_index_cache[0] != id(forward)
            or _reverse_index_cache[1] != len(forward)):
        _reverse_index_cache = (id(forward), len(forward), build_corp_to_stock_index(forward))
    return _reverse_index_cache[2].get(corp_code)
