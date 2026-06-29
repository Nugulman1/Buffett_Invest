"""
[작업1+2] corp_code 역인덱스 RED 박제.

박제할 동작:
 - apps.service.corp_code.build_corp_to_stock_index(forward) : {종목:corp} -> {corp:종목} 순수함수.
   한 corp에 복수 종목이 묶이면 보통주(끝자리 '0') 우선, 동급이면 사전순 최소(결정적).
 - apps.service.corp_code.get_stock_code_by_corp_code : 위 역인덱스로 대표코드 반환,
   동일 정방향 dict면 역인덱스 1회만 구축(캐시).

기대값 출처: 모두 사용자 명세 표(1~3행 + 4행)에서 직접 도출. 코드 출력 베끼지 않음.
추론 인터페이스: build_corp_to_stock_index(dict)->dict (인자·반환 순수 dict).
구현 전 RED 사유:
 - build_corp_to_stock_index 미존재(AttributeError).
 - get_stock_code_by_corp_code는 현재 삽입순서 의존 선형스캔(첫 매칭 반환)이라 결정적 대표선택 미적용.
"""
from unittest.mock import patch, MagicMock

import pytest

from apps.service import corp_code


# --- 작업1+2: build_corp_to_stock_index 순수함수 (명세 표 1~3행) ---

def test_build_reverse_index_basic():
    # 표 1행: 1:1 매핑은 그대로 역전
    forward = {"005930": "00126380", "000660": "00164779"}
    assert corp_code.build_corp_to_stock_index(forward) == {
        "00126380": "005930", "00164779": "000660",
    }


@pytest.mark.parametrize("forward", [
    {"005935": "00126380", "005930": "00126380"},   # 표 2행: 우선주 먼저 삽입
    {"005930": "00126380", "005935": "00126380"},   # 표 2행: 삽입순서 뒤집어도 같은 결과(결정성)
])
def test_build_reverse_index_prefers_common_stock(forward):
    # 끝자리 '0'(보통주) 우선 → 005930. 삽입순서 무관(결정적).
    assert corp_code.build_corp_to_stock_index(forward) == {"00126380": "005930"}


def test_build_reverse_index_no_common_stock_lexicographic_min():
    # 표 3행: 전부 우선주(끝자리≠0) → 사전순 최소 005935 (< 005937)
    forward = {"005937": "00126380", "005935": "00126380"}
    assert corp_code.build_corp_to_stock_index(forward) == {"00126380": "005935"}


# --- 작업1+2: get_stock_code_by_corp_code 결정적 대표선택 (표 4행) ---

@pytest.mark.parametrize("cache", [
    {"005930": "00126380", "005935": "00126380"},   # 보통주 먼저
    {"005935": "00126380", "005930": "00126380"},   # 뒤집어도 같은 결과(결정성)
])
def test_get_stock_code_returns_deterministic_representative(cache):
    fake_dart = MagicMock()
    fake_dart._corp_code_mapping_cache = cache
    with patch("apps.service.corp_code.DartClient", return_value=fake_dart):
        # 보통주(005930, 끝자리0) 우선 → 삽입순서와 무관하게 005930 (표 4행)
        assert corp_code.get_stock_code_by_corp_code("00126380") == "005930"


def test_get_stock_code_builds_reverse_index_once_and_caches():
    forward = {"005930": "00126380", "005935": "00126380"}  # 동일 dict 객체 재사용 → id 캐시
    fake_dart = MagicMock()
    fake_dart._corp_code_mapping_cache = forward
    # build_corp_to_stock_index를 카운팅 래퍼로 패치(명세상 보통주 대표 반환)
    counting = MagicMock(return_value={"00126380": "005930"})
    with patch("apps.service.corp_code.DartClient", return_value=fake_dart), \
         patch("apps.service.corp_code.build_corp_to_stock_index", counting):
        r1 = corp_code.get_stock_code_by_corp_code("00126380")
        r2 = corp_code.get_stock_code_by_corp_code("00126380")
    assert r1 == "005930" and r2 == "005930"   # 역인덱스가 돌려준 대표코드(표 4행)
    assert counting.call_count == 1            # 동일 정방향 dict → 역인덱스 1회만 구축(캐시)
