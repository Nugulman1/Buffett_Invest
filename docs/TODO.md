# TODO 리스트

## [최우선]
- **완료**: paste_parser — 연도·단위 추출, 표 본문 분리, rows JSON, 원 단위 정규화
- **완료**: 단위 처리 (_extract_unit_from_text, unit_multiplier)
- **완료**: 지표 추출·계산·DB 저장 — LLM(llm_extractor)로 rows에서 cfo/이자부채 등 추출 → IndicatorCalculator → DB

- 디버깅용 LLM 프롬포트 정리 (보류)
- **완료**: 기업 분석 홈페이지 기업번호(8자리) 조회 지원
- **완료**: 재무지표 계산기 국채수익률 페이지 로드 시 ECOS 데이터로 자동 채우기

## [보류]
- 실제 사용 영상 제작 (포트폴리오)

## [추후]
- 해외 기업까지 분석 기능 추가
- WACC 재계산 기능: 기대수익률·국채수익률 변경 시 FCF/ROIC/WACC만 재계산 (입력 데이터는 DB 유지)

## 참고사항
- DART API로 데이터를 제공하지 않는 기업은 자동으로 무시됨
