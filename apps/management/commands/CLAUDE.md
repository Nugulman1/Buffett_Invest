# apps/management/commands — 배치 명령어

루트 규칙 상속. 각 명령어의 부작용 범위와 실행 조건만.

## fetch_krx_daily

`python manage.py fetch_krx_daily [--no-market-cap]`
- 08:30 KST 이후이고 스냅샷 bas_dd가 오늘과 다르면 KRX API 호출 → JSON 스냅샷 저장 + 전 종목 시총·EV 갱신.
- **매일 08:30 cron 전제**. `--no-market-cap`이면 스냅샷만 갱신(시총 갱신 생략).

## recompute_second_filter

`python manage.py recompute_second_filter`
- `passed_second_filter IS NOT NULL`인 회사만 현재 roic/wacc로 재계산.
- **미평가(None)는 절대 건드리지 않음** — None→False는 "미평가"를 "탈락"으로 왜곡한다.
- roic/wacc 입력이 바뀐 뒤(마이그레이션 등)에만 수동 실행.

## backfill_valuation_indicators

`python manage.py backfill_valuation_indicators`
- DB 입력만으로 sustainable_growth·altman_z·zmijewski 재계산. **DART 재수집 없음.**
- **`load_company_from_db` 사용 금지** — current_assets 등 입력값을 덮어써 버린다.
  대신 `YearlyFinancialData` 행 직접 순회 + `update_fields=[...]`로 해당 필드만 저장.

## backup_memos / restore_memos

- `backup_memos [--output 파일]` — SELECT만, DB 변경 없음(기본 memos_backup.json).
- `restore_memos 파일 [--confirm]` — 메모 덮어쓰기. 기본은 경고 후 대기, `--confirm`으로 즉시 실행.
