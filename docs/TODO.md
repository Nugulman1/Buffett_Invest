# TODO 리스트

## [최우선]
- 코드 구조 전체적으로 점검 후 개선

## [완료]
- dart, ecos 제외한 데이터 수집처 정리 (docs/데이터 소스 정리.md) 및 KRX 시가총액·일별 데이터 연동
- LLM 배당금 추출 및 DB 저장 (복붙 현금흐름표 → dividend_paid 추출·YearlyFinancialData 저장·API 응답 포함)
- 1차/2차 필터 구조: 2차 필터 B안(DB), parse-paste 마지막 2차 통과 갱신, passed API DB 전환, JSON 제거
- 현금·비지배지분·EV/IC DB 저장, 부채비율 계산, calculate-ev-ic·market-cap API
- KRX 출력명 그대로 KrxDailyData 저장 (BAS_DD, IDX_CLSS, … MKTCAP)

## [보류]
- KRX API 키 발급 후 전체적인 기능 테스트

## [추후]
- 필터 조정해서 투자할 만한 기업 찾기
- 금리수익률 사용자 설정
- 배당금 테스트: 웹 계산기 복붙 시 확인

## 참고사항
- DART API로 데이터를 제공하지 않는 기업은 자동으로 무시됨
- KRX_API_KEY 없으면 KRX 조회 생략(에러 없음)
