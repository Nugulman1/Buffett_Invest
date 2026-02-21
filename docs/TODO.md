# TODO 리스트

## [최우선]
- (없음)

## [완료]
- 코스닥·코넥스 KRX 일별매매정보 수집 (유가·코스닥·코넥스 3시장, ksq_bydd_trd / knx_bydd_trd, 재수집 로직 적용)
- EV/IC 재무지표 계산(parse-paste) 시 계산·저장

## [보류]
- 

## [추후]
- 필터 조정해서 투자할 만한 기업 찾기
- 판관비율 수집 체크

## 참고사항
- **매출액 CAGR 필터**: 1차 필터의 매출액 CAGR(≥10%) 검사는 `apps/service/filter.py`의 `apply_all_filters`에서 주석 처리되어 있으며, 현재는 통과(True)로 고정되어 미적용 상태임.
- **KRX 데이터 수집**: 유가·코스닥·코넥스 3시장 일별매매정보 수집 적용됨. `ensure_latest_snapshot()`에서 재수집 조건(시장별 파일 없음 또는 bas_dd≠오늘 & 08:30 KST 이상) 시에만 API 호출. BASE_URL 고정 `https://data-dbg.krx.co.kr`, 하루 전·이틀 전 순 조회.

