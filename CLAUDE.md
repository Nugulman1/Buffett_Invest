# 투자 필터 백엔드 — 에이전트 가이드

Django 6 + DRF로 한국 상장사 ~2,850곳의 재무를 DART·ECOS·KRX에서 수집 →
지표 계산 → 2단계 필터·랭킹 → REST 조회하는 **장기투자 종목선별 백엔드**.

전체 조망은 `docs/아키텍처.md` 참조. 이 파일은 작업 시 지킬 규칙만.

## Where To Look

- **도메인 로직 전부** → `apps/service/` (앱의 심장, 별도 CLAUDE.md 有)
- **수집 조율** → `apps/service/orchestrator.py` (수집→계산→필터→저장)
- **웹 API** → `apps/companies/views/` (별도 CLAUDE.md 有)
- **URL 라우팅** → `config/urls.py`
- **ORM 모델 + 계산용 Python 객체** → `apps/models.py` (한 파일에 공존)
- **모든 튜닝 상수** → `config/settings.py` (필터 임계·랭킹 가중치·세율·병렬도)
- **배치 명령어** → `apps/management/commands/` (별도 CLAUDE.md 有)
- **테스트** → `tests/` (별도 CLAUDE.md 有)

## Commands

```bash
# 전체 수집 (종목코드.md → 100개 배치 병렬)
python collect_all_companies.py

# 테스트
python -m pytest                    # 전체
python -m pytest tests/test_calculator.py

# 배치 (상세는 apps/management/commands/CLAUDE.md)
python manage.py fetch_krx_daily            # 매일 08:30 KST 시총 갱신
python manage.py recompute_second_filter    # roic/wacc 변경 후 2차필터 재계산
python manage.py backfill_valuation_indicators  # 5선 지표 재계산(DART 재수집 없음)

python manage.py migrate
```

## Project Rules

- **미계산 = None 규약**: 지표 미산출은 `0`이 아니라 `None`으로 저장(EV·IC·ROIC·WACC·
  FCF·5선). `0`은 "실제 0"과 구분돼야 한다. 이걸 어기면 2차 필터가 미평가 회사를
  잘못 평가한다. `models.py`의 필드 주석과 service 로직이 이 규약에 의존.
- **튜닝 값은 하드코딩 금지** — 필터 임계·세율·ERP·가중치는 전부 `settings.py`에서
  읽는다. 매직넘버를 코드에 박지 말 것.
- **모델은 `apps/models.py` 단일 집중** — 앱별로 흩어지지 않음. 새 필드는 여기 + 마이그레이션.
- **SQLite WAL + 쓰기 락 재시도** — 모든 DB 쓰기는 `db.py`의 재시도 경로를 탄다.
  병렬 수집 중 "database is locked"는 정상(자동 재시도). 쓰기를 우회하지 말 것.

## Known Boundaries

- **DB는 SQLite 단일 파일**(`db.sqlite3`) — 대규모 동시 쓰기에 약함. 배치는 병렬도 12로 튜닝됨.
- **외부 API 3종 의존**: DART(재무)·ECOS(국채금리)·KRX(시총). 키는 `.env`.
- **시가총액은 배치 갱신 전제** — 일상 조회 뷰는 DB 저장값만 읽는다(전용 뷰 `get_market_cap`·
  `calculate_ev_ic`만 KRX 실시간). `fetch_krx_daily`가 매일 08:30 KST 안 돌면 시총·EV가 낡는다.
- **한글 파일명 사용**(`종목코드.md`, `docs/아키텍처.md`) — Windows 환경 기준.
