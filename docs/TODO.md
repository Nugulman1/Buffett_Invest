# TODO 리스트

## [최우선]
- (없음)

## [완료]
- 필터 통과 DB Index 넣어서 속도 향상 (Company 1차 필터 목록 조회 인덱스 적용)
- KRX 당일 전체 종목 JSON 스냅샷 저장·08:30 재수집·ISU_CD 조회·메모리 캐시 적용, KrxDailyData 제거
- 2차 미통과만 메인 필터 통과 리스트에서 제외 (passed_second_filter != False)
- clear_financial_data 시 분기보고서 보존
- 판관비율 DART fnlttCmpnyIndx 수집·DB 저장·상세 테이블 표기

## [보류]
- 

## [추후]
- 필터 조정해서 투자할 만한 기업 찾기

## 참고사항
- DART API로 데이터를 제공하지 않는 기업은 자동으로 무시됨
- 기업 조회 시 KRX 스냅샷으로 시가총액·EV/IC만 매 요청마다 갱신됨. 배당성향·2차 필터는 재무지표 계산기 저장 시에만 반영됨.
- **KRX**: 유가증권 일별매매정보(OPPUSES002_S2) 당일 전체 1회 호출 → `data/krx_daily_snapshot.json`에 15개 필드 저장·메모리 캐시. 재수집 조건: JSON 없음, 또는 bas_dd≠오늘(한국날짜)이고 현재 시각 08:30 KST 이상. `fetch_krx_daily` 관리 명령으로 08:30 스케줄 실행 권장. (주석 처리된 KRX 관련 코드가 있으면 보류/추가 절차 참고.)
- **매출액 CAGR 필터**: 1차 필터의 매출액 CAGR(≥10%) 검사는 `apps/service/filter.py`의 `apply_all_filters`에서 주석 처리되어 있으며, 현재는 통과(True)로 고정되어 미적용 상태임.
