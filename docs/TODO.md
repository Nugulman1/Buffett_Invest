# TODO 리스트

## [최우선]
- (없음)

## [완료]
- 기업 조회 시 EV/IC 자동 갱신 제거 (EV/IC는 계산기·parse-paste·calculate-ev-ic에서만 계산·저장)
- KRX 재수집 조건 수정 (저장된 bas_dd가 어제보다 이전일 때만 08:30 KST 이후 재수집)

## [보류]
- 

## [추후]
- 필터 조정해서 투자할 만한 기업 찾기
- 판관비율 수집 체크

## 참고사항
- **매출액 CAGR 필터**: 1차 필터의 매출액 CAGR(≥10%) 검사는 `apps/service/filter.py`의 `apply_all_filters`에서 주석 처리되어 있으며, 현재는 통과(True)로 고정되어 미적용 상태임.


