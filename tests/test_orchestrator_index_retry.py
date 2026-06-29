"""
[작업3] orchestrator 빈 인덱스 재시도 RED 박제.

박제할 동작(DataOrchestrator._ensure_krx_index):
 - 첫 로드 결과가 빈 dict면 캐싱하지 말고 다음 호출에서 재시도.
 - 비어있지 않으면 캐시(1회 로드, 기존 test_ensure_krx_index_builds_and_caches 계약 유지).
현재 버그: 빈 dict({})도 'is not None'이라 영구 캐싱 → 재시도 안 함.

기대값 출처: 사용자 명세(빈→재시도, 비어있지않음→캐시). SNAP은 비어있지 않은 재시도 성공분.
추론 인터페이스: DataOrchestrator()._ensure_krx_index()->dict.
구현 전 RED 사유: 빈 결과를 영구 캐싱하여 ensure_latest_snapshot이 1회만 호출됨(재시도 누락).
"""
from unittest.mock import patch

from apps.service.orchestrator import DataOrchestrator


# 비어있지 않은 스냅샷(재시도 성공분): _build_mktcap_index → {"005930": 400000000000}
SNAP = {"rows": [{"ISU_CD": "005930", "MKTCAP": "400,000,000,000"}]}


def test_ensure_krx_index_retries_on_empty_then_caches_nonempty():
    orch = DataOrchestrator()
    # 1차 None(→빈 인덱스), 2차 SNAP(→비어있지 않은 인덱스) 순서로 반환
    with patch("apps.service.krx_client.ensure_latest_snapshot",
               side_effect=[None, SNAP]) as m:
        idx1 = orch._ensure_krx_index()
        assert idx1 == {}                              # 첫 로드 비어있음
        idx2 = orch._ensure_krx_index()
        assert idx2 == {"005930": 400000000000}        # 재시도로 채워짐(명세에서 직접 도출)
        assert m.call_count == 2                       # 빈 결과는 재시도 → 2회 호출
