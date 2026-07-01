# apps/service — 도메인 로직

앱의 심장. views·commands·orchestrator는 여기를 부르는 얇은 껍질.
루트 규칙(미계산=None, 상수는 settings) 상속 — 아래는 이 레이어 고유 계약만.

## 공개 진입점 (다른 레이어가 호출)

- `calculator`: calculate_fcf / calculate_roic / calculate_wacc / compute_ic_ev / fill_valuation_indicators / flag_no_debt_suspect / flag_fcf_negative / count_consecutive_dividend_years
- `filter`: apply_all_filters / check_second_filter / evaluate_second_filter
- `db`: load_company_from_db / save_company_to_db / recompute_and_save_ev_ic / rank_passed_companies / 시총·국채·2차필터조회 게이트웨이(아래 DB 절)
- `krx_client`: fetch_and_save_company_market_cap / update_all_company_market_caps / serialize_krx_daily_row (스냅샷 파일캐싱은 `krx_cache.py`로 분리)
- `orchestrator`: collect_company_data / collect_companies_data_batch

## 계산 계약 (calculator.py)

- **FCF = CFO − |CAPEX|** (CAPEX 절대값; 음수는 자산처분이므로 부호 실수 주의).
- **ROIC/WACC**: tax_rate·ERP·buffer는 인자로 받음(기본값은 settings). 분모 0이면 `0.0`.
- **WACC Re = (국채수익률 + buffer 0.5%p + ERP) / 100**.
- **Altman Z''**(비제조): X4 분모(자본/부채)≤0이면 `None`. g/Z''/Zmijewski는 분모 불가 시 `None`.
- **g = ROIC × 유보율**, 유보율 = clamp(1 − 배당성향, 0, 1); 배당 None이면 유보율=1(무배당 간주).

## 이자부채 0/None 정책 (핵심)

이자부채가 falsy(0 또는 None)면 **IC·EV·ROIC·WACC 모두 None** 반환(무차입 의심).
계산하면 안 됨 — 2차 필터에서 제외되어야 한다. `compute_ic_ev`·`_fill_advanced_indicators`.

## 필터 (filter.py)

- 1차 윈도우: 최근 5년(부족하면 있는 만큼). None 값 행은 판정에서 제외.
- 규모별 ROE 임계: 대(≥10조)≥8% / 중견(5천억~10조)≥10% / 소(<5천억)≥12%. 최신 total_assets로 분류.
- 2차 윈도우: 최근 정확히 3년, roic·wacc 둘 다 not-None인 행만 평균.

## DB (db.py) — 게이트웨이

- **모든 service 모듈의 DB 접근은 db.py 함수 경유**(직접 `Model.objects...` 금지). 시총 쓰기=`update_company_market_cap`·`bulk_update_market_caps`, 국채=`get_or_create_bond_yield`, 2차필터 조회=`load_recent_roic_wacc`(roic/wacc dict)·`load_recent_yearly_data`(ORM 객체, no_debt_suspect용). filter→db는 순환 탓에 **함수내부 lazy import**.
  - **예외**: `orchestrator._ensure_bond_yield`는 조회+조건부갱신+ecos호출이 얽혀 db.py로 안 옮김 — `db_write_lock` 하에 직접 ORM 유지(의도적).
- 수집·지표 쓰기는 `run_with_write_lock_retry(fn, max_retries=5)` 경유(지수백오프).
  단 **favorites·quarterly 쓰기는 의도적으로 락 미적용**(db.py 주석) — 예외를 위반으로 오판 말 것.
- 로드 시 `interest_bearing_debt·interest_expense·cash_and_cash_equivalents·noncontrolling_interest` 4개는 `or 0`(WACC None 나눗셈 방지), 나머지 지표 필드는 None 보존.
- `nullify_uncomputed_indicators()`는 roic=0.0 **AND** wacc=0.0 이중조건(roic=0만은 보존).

## KRX (krx_client.py + krx_cache.py)

- **API 호출·시총 갱신·행 직렬화**는 `krx_client.py`, **스냅샷 파일캐싱**(`ensure_latest_snapshot` 등)은 `krx_cache.py`. krx_client가 캐싱 5심볼을 **re-export**하므로 `patch("apps.service.krx_client.ensure_latest_snapshot")` 패치 경로는 그대로 유효(모듈 글로벌 재바인딩).
- 재시도·timeout은 `settings.DATA_COLLECTION`에서: `API_MAX_RETRIES(+1=attempts)`·`KRX_RETRY_DELAY_SEC`·`API_TIMEOUT`. ecos도 `API_TIMEOUT` 참조.

## DART 추출 (dart_extractor.py)

- 계정 매칭은 **account_id 집합 멤버십 + 계정명 키워드 부분일치**(정규화 함수 안 씀).
  account_id 없는 회사(삼성 등)는 키워드 폴백 필수.
- 이자부채 집계는 **부호 유지(abs 금지)** — contra 계정(음수)이 자연 차감돼야 과대집계 방지. '소계/합계/총계' 계정은 중복가산 차단.
- CFS 먼저·없으면 OFS 폴백은 **orchestrator**가 수행(여기 아님). 안 하면 현금·차입금·CFO 미추출→지표 None.
- 이자비용 우선순위: CF 지급이자 > 이자비용 > 금융비용.

## Verification

- 순환 import 주의: `models.py` 객체가 `utils.normalize`를 함수 내부 lazy import(service↔models).
- `python -m pytest tests/test_calculator.py tests/test_filter.py tests/test_db.py tests/test_dart_extractor.py`
