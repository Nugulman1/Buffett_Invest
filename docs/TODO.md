# TODO 리스트

## [최우선] 

- [ ] UI 수정
- [ ] DB, 데이터 전체 수집 코드 확인
- [ ] 병렬 처리
- [ ] 1차 필터 성공한 기업 리스트 반환

## [완료]
- [x] 기업 자동 수집 기능 (`collect_all_companies` 관리 명령어 생성)
  - 종목코드.md 파일 기반 대량 수집
  - 수집 진행 상태 관리 (collected_stock_codes.txt)
  - 필터 통과 기업 목록 저장 (passed_filters_stock_codes.txt)
  - 4월 1일 기준 재수집 로직
  - XML 캐싱을 통한 종목코드 변환 최적화