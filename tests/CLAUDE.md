# tests — 회귀 방지 · RED 박제

pytest + pytest-django. 설정 `DJANGO_SETTINGS_MODULE=config.settings`(pytest.ini).
**conftest.py 없음** — 각 test 파일이 `_make_*()` 로컬 헬퍼로 픽스처를 직접 조립.

## 실행

`python -m pytest` (전체) / `python -m pytest tests/test_calculator.py`

## 파일 종류

- **test_*_redteam.py** — RED 박제. 파일 헤더에 "기대값 출처"를 명시(구현 출력을 베끼지
  않고 아젠다 의도·파이프라인 진실에서 도출). 구현 전 실패 상태로 박제한다.
- **test_*.py** — characterization. 현재 동작을 캡처하되, 정정 대상은
  `@pytest.mark.xfail(strict=True)`로 두어 수정 시 xpass로 자동 신호.

## 패턴

- **DB 접근**: `@pytest.mark.django_db`(함수/클래스). Django TestCase 아님, raw ORM `.objects.create()`.
- **순수함수 테스트**: 마크 불필요. `YearlyFinancialDataObject` / `CompanyFinancialObject` /
  `SimpleNamespace`로 메모리 객체 구성(DB 미접근).
- **외부 API 목킹**: `unittest.mock.patch()` (responses 라이브러리 안 씀).
  `side_effect=[v1, v2]`로 재시도 시퀀스, `assert_called_once_with()`로 호출 검증.
- **API 테스트**: DRF `APIClient()` + `@pytest.mark.django_db`, corp_code는 8자리 사용(DART 호출 회피).
- **부동소수점**: `pytest.approx()`. assert 메시지에 기대 로직과 실제값을 함께.

## 커버 집중 영역

calculator(순수함수, tax_rate·erp 인자화로 결정적) / filter(1차 순수 + 2차 DB) /
orchestrator(KRX 시총 캐싱·재시도) / dart_extractor(계정 매핑·부호 규칙) /
db(ORM 계약) / api_favorites(HTTP 응답 동등성).

## 새 테스트 추가 시

파일명 `test_<모듈>.py`(레드팀이면 `_redteam` 접미). 기대값은 명세/주석에서 독립 도출 —
구현 출력 복붙 금지(순환논리).
