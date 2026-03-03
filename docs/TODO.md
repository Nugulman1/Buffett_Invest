# TODO 리스트

## [최우선]
- 

## [완료]
- 

## [보류]
- 

## [추후]
- 

## 참고사항
- **매출액 CAGR 필터**: 1차 필터의 매출액 CAGR(≥10%) 검사는 `apps/service/filter.py`의 `apply_all_filters`에서 주석 처리되어 있으며, 현재는 통과(True)로 고정되어 미적용 상태임.
- **KRX 재수집 로직**: `apps/service/krx_client.py`의 `_should_refresh_snapshot`에서 일시적 주석 처리됨. 현재 `return False`로 고정되어 기존 JSON 스냅샷만 사용함.


