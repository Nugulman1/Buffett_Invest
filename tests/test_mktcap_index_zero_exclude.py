"""
[기준 B] 시총 인덱싱 단일 진실원 + 0 이하 제외 RED 박제.

박제할 동작(_build_mktcap_index(snap)):
 (1) ISU_CD -> int(MKTCAP) 매핑, 콤마 제거 파싱("1,234,567" -> 1234567)
 (2) ISU_CD 빈 값 / MKTCAP 빈 값 행 제외
 (3) MKTCAP "0" 또는 0 이하로 파싱되는 행 제외 (거래정지 종목 market_cap=0 이 EV 왜곡 방지)
 (4) 파싱 불가 행 제외
추가: orchestrator._ensure_krx_index 도 동일 인덱싱 결과를 내야 함(단일 진실원).

구현 전 RED 사유: 현재 두 함수 모두 'MKTCAP=0/음수' 를 제외하지 않아 인덱스에 0/음수가
포함됨. 기대값 출처: 모두 위 규칙(기준 B 본문)에서 직접 도출. 코드 출력 베끼지 않음.
추론한 인터페이스: krx_client._build_mktcap_index(dict)->dict,
orchestrator.DataOrchestrator()._ensure_krx_index()->dict.
"""
from unittest.mock import patch

from apps.service import krx_client
from apps.service.orchestrator import DataOrchestrator


SNAP_B = {"rows": [
    {"ISU_CD": "100000", "MKTCAP": "1,234,567"},     # 콤마 파싱 → 1234567
    {"ISU_CD": "200000", "MKTCAP": "500000000000"},  # 정상 → 500000000000
    {"ISU_CD": "300000", "MKTCAP": "0"},             # 0 → 제외(규칙3)
    {"ISU_CD": "400000", "MKTCAP": "-100"},          # 0 이하 → 제외(규칙3)
    {"ISU_CD": "500000", "MKTCAP": ""},              # 빈 시총 → 제외(규칙2)
    {"ISU_CD": "", "MKTCAP": "9,999"},               # 빈 종목코드 → 제외(규칙2)
    {"ISU_CD": "600000", "MKTCAP": "abc"},           # 파싱 불가 → 제외(규칙4)
]}

# 규칙(1)(2)(3)(4)에서 직접 도출한 기대 인덱스
EXPECTED = {"100000": 1234567, "200000": 500000000000}


def test_build_mktcap_index_excludes_zero_and_nonpositive():
    """_build_mktcap_index: 콤마 파싱·빈값/파싱불가 제외 + 0/음수 제외(기준 B)."""
    assert krx_client._build_mktcap_index(SNAP_B) == EXPECTED


def test_ensure_krx_index_matches_spec_and_build():
    """orchestrator._ensure_krx_index 가 _build_mktcap_index 와 동일 결과(단일 진실원)."""
    orch = DataOrchestrator()
    orch._krx_index = None  # 캐시 무효화
    with patch("apps.service.krx_client.ensure_latest_snapshot", return_value=SNAP_B):
        idx = orch._ensure_krx_index()
    # 규칙에서 도출한 기대값과 일치(0/음수 제외) → 현재 RED
    assert idx == EXPECTED
    # 단일 진실원: _build_mktcap_index 와도 동일해야
    assert idx == krx_client._build_mktcap_index(SNAP_B)
