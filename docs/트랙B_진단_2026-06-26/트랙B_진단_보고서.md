# 트랙 B 진단 보고서 — 지표·리서치·코드 구조

> 작성일: 2026-06-26
> 범위: 트랙 B(기존 가치필터 보완 + 리팩터링) 사전 진단
> 구성: ① 현재 지표 복기·평가 ② 추가 지표 + 입수법 리서치 ③ 토스 Open API ④ 코드 구조 리뷰 ⑤ 종합·실행 순서

---

## 0. 핵심 결론 (한 문단)

트랙 B의 진짜 문제는 "지표가 부족한 것"이 아니라 **이미 만든 엔진이 안 돌아가는 것**이다.
ROIC/WACC가 자동수집에서 안 채워지고(§1·§4 동시 확인), KRX 재수집이 코드로 영구 차단돼
EV가 항상 낡은 주가로 계산되며(§4), 테스트가 0개라 이걸 고쳐도 안전망이 없다(§4).
**새 지표 추가(§2)보다 이 셋을 먼저 고쳐야** 무엇을 추가하든 의미가 생긴다.

가장 신뢰도 높은 수정 대상 = 지표 평가(§1)와 코드 리뷰(§4)가 **독립적으로 같은 결론**에 도달한 지점:
ROIC/WACC 자동수집 부재, EV 입력 신뢰성(낡은 주가·이중경로·현금 불일치), 죽은/오해 코드.

---

## 1. 현재 지표 복기 + 평가

### 평가 요약

| 등급 | 문제 | 한 줄 |
|---|---|---|
| 🔴 치명 | ROIC/WACC가 자동수집에서 안 채워짐 | 2차 필터가 "수동 붙여넣기한 기업"에만 작동 → 스크리너가 반쪽 |
| 🔴 치명 | 부채비율 정의가 역수 | `자본/부채`로 계산 → UI "부채비율"을 거꾸로 읽게 됨 |
| 🟡 주의 | 현금 처리 불일치 | EV는 현금×70%, ROIC/IC는 현금 전액 → 같은 현금을 다르게 |
| 🟡 주의 | WACC의 Re가 일률적 | ERP 10% 고정 + 베타 없음 → 모든 기업에 같은 자본비용 |

### 필터에 실제로 쓰는 지표

**1차 퀄리티 필터 (5개 중 4개 작동)**
- **영업이익(적자 ≤1회) + 당기순이익(5년 합>0)**: 적자기업 거름. 타당. 단 둘 다 "이익의 부호"만 봄 — 이익의 *질*(현금화 여부)은 미검증 → accrual/FCF로 보완 여지(§2).
- **영업이익률 평균 ≥10% + ROE 규모별(8/10/12%)**: 둘 다 **수익성 축**이라 정보가 겹친다. 영업이익률 높은 기업은 ROE도 높은 경향 → 두 필터가 사실상 같은 기업을 거른다. 다양성 부족. 규모별 차등(소형주 12%)은 근거 있고 좋다.
- **매출 CAGR ≥10%**: 코드에 있으나 `True` 고정, **미적용** → 지금 필터엔 **성장 축이 없다.**

**2차 필터 (ROIC−WACC ≥ 2%p)**
- 개념은 이 프로그램의 **가장 강한 무기**. "자본비용 초과 수익 = 경제적 해자"를 직접 판별.
- 🔴 그런데 ROIC/WACC는 배치 수집에서 계산·저장되지 않음. `calculate_all_indicators`는 사실상 빈 함수(`calculator.py:256~279`), 실제 채움은 `parse-paste`(수동 붙여넣기)에서만 → **2차 필터를 통과하려면 기업마다 수동 처리 필요.** 자동 스크리닝이 끊김. 단일 최대 문제.

### 계산만 하고 안 쓰는 지표
- **EV / IC / EV-IC**: 가격 축인데 필터 미사용 → 트랙 A(저평가)에서 채울 공백.
- **FCF**: 계산되지만 어디에도 안 들어감. 이익의 질을 볼 좋은 재료가 놀고 있음.
- **부채비율**: 🔴 `calculate_debt_ratio = 자본총계/부채총계`(`calculator.py:318~324`). 표준 부채비율은 **부채/자본** → 지금 건 그 **역수**. 값이 클수록 안전한데 이름은 "부채비율"이라 *클수록 위험*으로 읽힘 — 해석이 거꾸로.
- **ICR**: `finance_costs` 참조 버그(존재하지 않는 속성) + 미사용. 죽은 코드.
- **배당성향 = 배당/FCF**: 표준(배당/순이익)과 다른 변형. FCF 음수면 의미 깨짐.

### 설정값
- **세율 25% 고정**: 실효세율 대신 단순화. 수용 가능하나 면세·이월결손 기업 왜곡.
- **WACC Re = 국채 + 0.5%p + ERP 10%**: ERP 10%는 한국 통상치(6~8%)보다 높음. **CAPM 베타 없어 전 기업 동일 Re** → 업종 위험 미반영. 2%p 정밀 문턱 대비 자본비용은 거침(비대칭).
- **현금 70%(EV) vs 현금 전액(IC/ROIC)**: 같은 현금을 다르게 → EV/IC 비율의 분자·분모 정의 불일치.

### 잘한 점 (근거와 함께)
- ROIC−WACC를 핵심 판정에 쓴 것: 회계이익이 아니라 경제적 부가가치로 봄. 가치투자 정석.
- 규모별 ROE 차등: 소형주 ROE 인플레 보정. 합리적.
- None 연도 일관 제외: 데이터 품질 방어 일관.
- 현금 보수적 반영(EV): 방향 옳음(IC와 불일치가 문제일 뿐).

**요약**: 지표 *선택*은 정석. 고칠 건 (1) ROIC/WACC 자동계산 연결, (2) 부채비율 역수 정정, (3) 현금 처리 통일, (4) 미적용 성장 축·노는 FCF 활용. EV/IC 가격 축은 트랙 A.

---

## 2. 추가 지표 + 입수법 리서치

**1순위 = GP/A (매출총이익/총자산).** 한국 백테스트 단일 퀄리티 지표 *1위*, 추가 수집 0(이미 받는
매출·매출원가·자산총계로 즉시 계산), ROE·영업이익률과 직교 → §1의 "수익성 축 중복"을 정확히 메움.

### 추천 Top 10

| # | 지표 | 메우는 약점 | 한국 유효성 근거 | 입수 경로 | 난이도 |
|---|------|-----------|----------------|----------|--------|
| 1 | **GP/A = (매출−매출원가)/총자산** | ROE/영업이익률은 회계조정·레버리지 민감. GP/A는 손익 맨 위라 조작 여지 적고 직교 | 국내 백테스트 GP 전체기간 최우수(KCI); 美 GP 월0.54%>HML0.40%(Novy-Marx 2013) | DART 손익+자산총계. **이미 수집** | **즉시** |
| 2 | **가격배수 PER·PBR·EV/EBIT·FCF yield** | 가장 큰 공백=가격 축. 퀄리티만 보고 비싸게 사는 위험 차단 | 가치×퀄리티 결합 한국서 유효(KCI) | KIS Developers PER/PBR/EPS/BPS 직접제공; 또는 KRX·DART주식수×종가 | 추가수집(시세) |
| 3 | **발생액 = (순이익−CFO)/평균총자산** | 순이익·ROE 필터 통과한 "현금 안 들어오는 이익" 적발. 이익의 질 축 전무 | Sloan(1996) 저발생액 롱숏 연12%; 한국 혼재→하방방어용 | DART CFO+순이익. **이미 수집** | 즉시 |
| 4 | **순부채/EBITDA** | 현 부채비율(자본/부채)은 장부·업종편차 큼. 상환능력 정규화 | 솔벤시 글로벌 표준 | DART (차입금−현금)/(영업이익+감가상각) | 추가수집 일부 |
| 5 | **다년 평균 ICR(정상화)** | 현재 ICR은 1년치만 → 일회성에 흔들림 | 부실위험 회피 표준 | DART 영업이익/이자비용(이미 계산), 다년평균만 | 즉시 |
| 6 | **현금전환율 CFO/영업이익** | 영업이익률의 현금 뒷받침 검증. 흑자도산 조기경보 | 발생액 이론의 현금흐름 버전 | DART CFO/영업이익. **이미 수집** | 즉시 |
| 7 | **총주주수익률=(배당+자사주순매입)/시총** | 현 배당성향은 지급비율만. 가격대비 수익률+자사주(코디 핵심) 누락 | 주주환원·밸류업이 한국 저평가 해소 핵심 | DART 배당+자기주식/시총은 KIS·KRX | 추가수집+시세 |
| 8 | **내재성장률 g=재투자율×ROIC** | 미적용 매출CAGR(후행) 대체. 성장의 질 | 가치창출=ROIC>WACC 재투자(McKinsey) | DART (1−배당성향)×ROIC. **이미 계산** | 즉시 |
| 9 | **자산성장률(저자산성장)** | 과잉투자·M&A로 자산만 불린 기업 회피 | 자산성장 이상현상 국제적 광범위(Cooper et al.) | DART 자산총계 전년대비. **이미 수집** | 즉시 |
| 10 | **Piotroski F-score(9개 합성)** | 개별 퀄리티를 합성 점수로 묶어 노이즈 감소 | 한국 수정 F-score 유의한 양의 초과수익(KCI); 美 고F 연13.4%vs5.9% | DART 다년 9개 항목 | 추가수집 일부 |

> 보너스(선택) — **Beneish M-score**: 분식 8변수, 美 조작기업 76% 적발/오탐 17.5%. 데이터 8종 추가 + 한국 효과성 미확인. 발생액(#3)이 대부분 커버 → 후순위.

### 우선순위 3개 (ROI순)
1. **GP/A** — 추가수집 0, 한국 1위, 직교. 노력 대비 효과 압도적.
2. **가격배수** — 구조적 공백. 가장 중요하나 KIS 연동 인프라 비용 동반.
3. **발생액** — 싸고 강한 하방방어. CFO 이미 수집 → 추가비용 거의 0.

> 1·3번은 추가수집 없이 코드만 추가하는 즉효, 2번은 전략적 중요도 최상이나 KIS 연동 필요.

---

## 3. 토스 Open API 실태 + 시세·가격배수 입수 대안

**결론: 토스는 부적합.** 토스 Open API(2026 정식오픈)는 시세·주문용 — Auth/Market Data(호가·체결·캔들)/Stock Info/Market Info(환율·휴장일)/Account/Order **6종뿐, 재무제표·PER·PBR·EPS 미제공.** 가격배수를 직접 못 받음.

| 소스 | 무료 | 제공데이터 | 인증/제약 |
|------|-----|-----------|----------|
| **토스 Open API** | 무료 | 시세(호가·체결·캔들)·종목마스터·환율. **PER/PBR/재무 없음** | OAuth2, 토스계좌 필요 |
| **KIS Developers(한투)** ★추천 | 무료 | 기본시세에 **PER/PBR/EPS/BPS**, 별도 재무비율 API(매출증가율·ROE·EPS·BPS·부채비율), 차트·순위·재무 | OAuth(앱키/시크릿), 계좌 필요, 초당 호출제한 |
| **KRX OPEN API(openapi.krx.co.kr)** | 무료 | 일별매매정보(OHLCV·시총)·종목기본정보·지수. **개별종목 PER/PBR 미명시(미확인)** | 인증키+서비스별 개별승인, 승인~1일 |
| **KRX Data Marketplace 웹(data.krx.co.kr)** | 무료 | **개별종목 PER/PBR/배당수익률** 조회·엑셀 | 로그인 필요, 공식API 아님 → pykrx `get_market_fundamental` 우회 |
| **OpenDART(이미 사용중)** | 무료 | 재무제표·배당·자사주(배수의 분모) | API키, 분당 호출제한 |

**가격배수 입수 결론**: 완성된 PER/PBR은 **KIS Developers**가 최선(무료·API·개인가능). EV/EBIT·FCF yield 같은 고유 배수는 **시총/주가만 KIS·KRX로 받고 분모는 기존 DART**로 조합. pykrx는 웹스크래핑이라 백업으로만.

---

## 4. 코드 구조 리뷰 (기존 `코드검사_개선사항.md` 이슈 제외, 신규)

**가장 큰 구조적 약점**: 계산 정확성이 생명인 금융 앱인데 — (1) 테스트 0개, (2) 비즈니스 로직이 뷰에 통째로 들어가 `db.py`가 선언한 "뷰는 ORM 직접 사용 안 함" 계약이 깨짐, (3) KRX 시가총액 재수집이 코드로 영구 비활성화돼 EV가 항상 낡은 주가로 계산.

### 🔴 높음
- **KRX 재수집 영구 비활성화** (`krx_client.py:173-174`): `_should_refresh_snapshot` 첫 줄 `return False`로 전체 차단 → `ensure_latest_snapshot`이 API 미호출 → market_cap이 정적 JSON에 고정 → EV·EV/IC가 영구히 낡은 주가. **권장**: 디버깅 종료 후 `return False` 제거·주석 복원, 최소한 stale 경고 로그.
- **테스트 전무**: 앱 코드에 `test*.py` 0개. ROIC/WACC/EV/FCF/CAGR이 앱의 존재 이유인데 회귀 안전망 없음. 순수함수라 테스트가 가장 쉬운데도. **권장**: calculator 6공식 + filter 5필터부터 단위테스트(% vs 소수 경계 포함).
- **레이어 계약 위반** (`api_financial.py`, `api_misc.py` 전반): `db.py` docstring은 "뷰는 db 모듈·DART 서비스만, ORM 직접 금지"인데 뷰가 `get_model` + `.objects.get/save/update/filter`를 도처에서 직접 사용. `db_write_lock` 등 영속화 규칙이 뷰에서 무시됨. **권장**: ORM 접근을 db.py로 모으거나 계약 문구를 현실에 맞게 수정(택1).
- **God-function** `parse_and_calculate` (`api_financial.py:250-519`): 단일 뷰 ~270줄에 파싱·LLM·KRX·계산·영속화·배당성향·EV/IC·2차필터·로깅 혼재. **권장**: service/로 추출, 뷰는 요청 파싱+호출만.
- **쓰기 동시성 보호 누수** (`db.py:182` 락 ↔ 뷰 저장들): `db_write_lock`은 `save_company_to_db`·채권저장만 보호. 뷰의 `yearly_data_db.save()`(`api_financial.py:477`), `yd.save()`(`:651`), 메모, market_cap update(`krx_client.py:365`), 2차필터 save는 락·재시도 없음. SQLite WAL 미설정(`settings.py:78`). PARALLEL_WORKERS=9 배치와 멀티스레드 요청이 겹치면 "database is locked" 그대로 실패. **권장**: PRAGMA journal_mode=WAL, 쓰기를 락+재시도 헬퍼로 일원화.

### 🟡 중간
- **EV/IC 이중 계산 경로** (`api_financial.py:463-477` vs `582-651`): parse는 LLM 추출값, calculate_ev_ic는 DB 저장값으로 각각 계산·저장 → 마지막에 돈 엔드포인트에 따라 EV drift. **권장**: 단일 함수화, 입력 소스 고정.
- **orchestrator 단건/배치 중복** (`orchestrator.py:109-138` ↔ `179-200, 220-227`): 채권수익률 캐싱·ROE→판관비→계산→필터→저장 시퀀스 복붙(단건엔 try/except, 배치엔 일부 없음). **권장**: 공통 헬퍼(`_ensure_bond_yield`, `_finalize_company`) 추출.
- **total_equity vs equity 이중 필드** (`models.py:309,330`; `db.py:148-173`): ROIC/IC/WACC는 `equity`만 사용인데 `load_company_from_db`는 equity 미세팅 → DB로드 객체에 calculator 호출 시 equity=0 → ROIC/IC 0. **권장**: equity를 total_equity property로 만들거나 필드 통합.
- **채권수익률 단위 불일치** (`bond_yield.py:9` 소수 vs `calculator.py:235` % vs `api_financial.py:296` 3.5% vs `:83` 소수): 엔드포인트마다 단위 상이 → WACC에 소수 넣으면 채권 기여분 무시. **권장**: WACC 입력을 소수로 통일, 한 곳에서만 변환, 매직 3.5 제거.
- **죽은/오해 코드** (`calculator.py:256-279`, `filter.py:192`): `calculate_all_indicators` no-op, `filter_revenue_cagr=True` 하드코딩인데 저장·AND 연산 유지. **권장**: no-op 제거, 미사용 필터 명시 비활성화/제거.
- **매직넘버 산재** (`calculator.py:185` 현금 0.7, `:235` +0.5%p, `models.py:337-338` beta 1.0/mrp 5.0 미사용, `api_financial.py:296`·`pages.py:41` 3.5): settings로 이동, 미사용 필드 제거.

### 🟢 낮음
- 분기 ROE 0.0 고정(`db.py:68`) / corp_code XML 로드 비스레드세이프(`dart/client.py:191,289`) / flush_daily_stats 락 미보유(`dart/client.py:257-274`) / None·0 의미 혼재(`models.py:306-313`).

### 구조 개선 우선순위 Top 5
1. KRX 재수집 복원(`krx_client.py:174`) — EV 영구 낡은 값. 즉시.
2. calculator + filter 단위테스트 — 순수함수라 비용 최소, 보호 최대.
3. parse_and_calculate 서비스 추출 + 뷰 ORM을 db.py로 — 레이어 계약 복원, 락 일원화 전제.
4. SQLite WAL + 쓰기 락/재시도 일원화 — PARALLEL_WORKERS=9 × 멀티스레드 충돌 해소.
5. EV/IC·채권수익률 단위·계산 경로 단일화 — 지표 drift 제거.

### 확인 필요 (단정 안 함)
- (a) 채권수익률이 실제 프론트에서 %로 전달되는지(`detail.html`/`calculator.html` 미확인)
- (b) KRX ISU_CD 매칭이 6자리 종목코드와 일치하는지(`krx_client.py:301`)

---

## 5. 종합 — 교차 발견 + 트랙 B 실행 순서

### 교차 발견 (§1 지표평가 ∩ §4 코드리뷰 = 최우선)

| 문제 | §1(지표) | §4(코드) |
|---|---|---|
| ROIC/WACC 자동수집 안 됨 | "2차 필터가 반쪽" | `calculate_all_indicators` no-op |
| EV 입력 신뢰성 | "현금 처리 불일치" | "KRX 재수집 차단 → 낡은 주가" + "EV 이중경로" |
| 죽은/오해 코드 | ICR 버그·부채비율 역수 | no-op·하드코딩·매직넘버 |

### 트랙 B 실행 순서

**1단계 (엔진 복구, 신규 추가 전 필수)**
1. KRX 재수집 `return False` 제거 (EV 정확성)
2. ROIC/WACC를 배치 수집 파이프라인에 연결 (2차 필터 자동화)
   - **병목 재정의**: 외부 완성값 부재가 아님. ROIC/WACC 입력(이자부채·이자비용·CFO·CAPEX·현금)을 현재 **LLM이 붙여넣기 텍스트에서 추출**(`api_financial.py:300-470`)해 수동 기업만 채워짐. WACC는 CAPM 베타 미사용(§1)이라 **베타 자동수집 불필요.**
   - **제안 경로**: 현 주요계정 API 대신 **DART `fnlttSinglAcntAll.json`(전체 재무제표) 추가** — 단기차입금·장기차입금·사채·리스부채(이자부채), 영업활동현금흐름·유형자산취득(CFO·CAPEX), 현금·비지배지분을 계정과목 단위로 자동 수집 → LLM 추출(`extract_financial_indicators`)을 DART 파서로 대체, `calculate_roic/wacc`는 재사용. 비용 0, 기존 키 그대로, ToS 리스크 없음.
   - ⚠ **검증 필수**: 이자비용은 일부 종목에서 손익본문이 아니라 **주석(금융원가)에만** 있어 누락 가능 → Rd·이자부채에 직결되므로 금융비용 근사 폴백 + 이 계정 단위테스트 필요.
   - (선택) 세율 25% 고정 → 법인세비용÷세전이익 기업별 실효세율, ERP는 다모다란 한국치 연1회 갱신.
3. calculator·filter 단위테스트 (이후 모든 변경의 안전망)

**2단계 (정합성)**
4. 부채비율 역수 정정 + 현금 처리 통일 + 채권수익률 단위 통일 + EV/IC 단일 함수화

**3단계 (지표 확장)**
5. GP/A·발생액 추가 (공짜) → 6. KIS Developers 연동해 가격배수 (트랙 A 저평가 스크리너와 직결)

> 1·2단계 없이 5·6단계부터 하면 **낡은/안 도는 토대 위에 지표만 쌓는 꼴.**

---

## 부록 — 출처 (§2·§3 리서치)

- KCI 「국내 주식시장에서의 퀄리티 투자전략」: https://www.kci.go.kr/kciportal/ci/sereArticleSearch/ciSereArtiView.kci?sereArticleSearchBean.artiId=ART003011873
- Novy-Marx (2013) Gross Profitability Anomaly, JFE: https://oldschoolvalue-files.s3.amazonaws.com/pdf/Novy-Marx_Gross-Profitability-Anomaly_JFE_2013.pdf
- Percent accruals: Korean evidence: https://www.sciencedirect.com/science/article/abs/pii/S0927538X15000293
- Piotroski F-score 유용성(KISS): https://kiss.kstudy.com/thesis/thesis-view.asp?key=2345775
- F-score 백테스트(Quant-investing): https://www.quant-investing.com/blog/piotroski-f-score-back-test
- Beneish (1999) Earnings Manipulation: https://www.researchgate.net/publication/252059255_The_Detection_of_Earnings_Manipulation
- 토스 Open API docs: https://developers.tossinvest.com/llms.txt / https://corp.tossinvest.com/ko/open-api
- KIS Developers: https://apiportal.koreainvestment.com/apiservice / https://github.com/koreainvestment/open-trading-api
- KRX OPEN API: https://openapi.krx.co.kr/
- KRX Data Marketplace: https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020502
- OpenDART 배당/자기주식: https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2019005

### 미확인 사항
1. KRX OPEN API의 개별종목 PER/PBR 제공 여부 (서비스목록 미명시 — 신청해 확인 필요)
2. Beneish M-score 한국 효과성 (국내 실증 미발견)
3. KCI 논문의 구체 백테스트 기간·수익률 (초록만 공개)
