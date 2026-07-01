# apps/companies/views — 웹 API

루트 규칙 상속. 아래는 이 계층 고유 함정만.

## 구성

- `api_financial.py` — 재무·ROIC/WACC·계산기·연/분기 조회
- `api_misc.py` — 필터 통과 목록·검색
- `api_favorites.py` — 즐겨찾기 CRUD
- `pages.py` — HTML 페이지 렌더 (여기만 순수 Django, 나머지는 DRF)

## 반드시 지킬 것

- **corp_code 정규화**: corp_code를 받는 뷰(단건 조회·계산·메모 등)는 6자리(종목코드)·
  8자리(기업번호)를 혼용 입력받으므로 **초입에서 `resolve_corp_code(corp_code)` 호출** 필수 —
  누락하면 6자리 조회가 깨진다. (passed·search 등 목록 뷰는 corp_code 인자 없음.)
- **URL 순서 의존**(`config/urls.py`): 고정경로(`/passed/`·`/search/`·`/favorites/`)는
  `<str:corp_code>` 패턴보다 **먼저** 와야 한다. Django는 순차 매칭이라 순서가 바뀌면
  `/search`를 corp_code로 오인해 단건 조회가 깨진다. 새 고정경로 추가 시 위쪽에.
- **응답 규약**(DRF): `Response(data, status=HTTP_...)`. 에러는 `Response({"error": "msg"}, status=...)`.
- **시가총액**: 조회 뷰(`get_financial_data` 등)는 DB 저장값만 읽음(lazy KRX 제거됨) —
  일상 갱신은 `fetch_krx_daily` 배치. **단 전용 뷰 `get_market_cap`·`calculate_ev_ic`는
  의도적으로 KRX 실시간 폴백**을 한다(이 둘은 예외).

## get_passed_companies 정책

1차 통과 기업을 노출하되 **2차 미통과만 제외** — 미평가·통과는 모두 노출(2차는 선택 평가).

## Verification

`python -m pytest tests/test_api_favorites.py` (APIClient characterization, 응답 동등성 보증)
