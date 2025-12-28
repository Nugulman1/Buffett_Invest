# XBRL 데이터 수집 디버깅 보고서

## 개요
삼성전자 XBRL 데이터 수집 시 여러 지표(equity, cash, borrowings 등)가 0으로 수집되는 문제를 디버깅하고 해결한 과정을 정리한 문서입니다.

## 발견된 문제점

### 문제 1: YearlyFinancialData 객체가 None인 상태에서 속성 할당 시도

**증상:**
- XBRL 데이터 수집 시 `AttributeError: 'NoneType' object has no attribute 'tangible_asset_acquisition'` 발생
- 예외가 조용히 처리되어 데이터가 수집되지 않음

**원인:**
- `collect_xbrl_indicators` 함수에서 `yearly_data`를 찾지 못하면 `None`으로 남음
- 이후 `yearly_data.tangible_asset_acquisition = ...` 같은 속성 할당 시도 시 에러 발생
- `fill_basic_indicators`에서 `yearly_data`를 생성하지만, XBRL 수집만 하는 경우에는 생성되지 않음

**수정 파일:** `apps/service/dart.py`

**수정 내용:**
```python
# 해당 연도의 YearlyFinancialData 찾기
yearly_data = None
for yd in company_data.yearly_data:
    if yd.year == year:
        yearly_data = yd
        break

# YearlyFinancialData가 없으면 생성
if yearly_data is None:
    yearly_data = YearlyFinancialData(year=year, corp_code=corp_code)
    company_data.yearly_data.append(yearly_data)
```

---

### 문제 2: filter_context 함수가 재무상태표 항목을 필터링하여 제외

**증상:**
- 재무상태표 관련 지표들(equity, cash_and_cash_equivalents, borrowings, bonds 등)이 모두 0으로 수집됨
- acode_index에 해당 ACODE들이 포함되지 않음
- `filtered_count`가 6017개로 높음 (재무상태표 항목들이 대부분 제외됨)

**원인:**
- `filter_context` 함수가 `dFY` (duration Fiscal Year)만 허용
- 재무상태표 항목들은 `eFY` (ending Fiscal Year)를 사용
- XBRL 표준에서:
  - **dFY (duration Fiscal Year)**: 기간 데이터 (현금흐름표, 손익계산서)
  - **eFY (ending Fiscal Year)**: 시점 데이터 (재무상태표)

**수정 파일:** `apps/service/xbrl_parser.py`

**수정 전:**
```python
# 연간만 채택 (dFY = duration Fiscal Year, 분기 제외)
if 'dFY' not in context_ref:
    return False
```

**수정 후:**
```python
# 연간만 채택
# - dFY (duration Fiscal Year): 현금흐름표, 손익계산서용 (기간)
# - eFY (ending Fiscal Year): 재무상태표용 (시점)
if 'dFY' not in context_ref and 'eFY' not in context_ref:
    return False
```

**수정 결과:**
- `acode_index_size`: 76개 → 133개 (57개 증가)
- `matched_count`: 232개 → 344개 (112개 증가)
- `filtered_count`: 6017개 → 5905개 (112개 감소)

---

### 문제 3: ACODE 이름 불일치 (대소문자 차이)

**증상:**
- `current_portion_of_long_term_borrowings` 지표가 0으로 수집됨
- 매칭 테이블에는 있지만 실제 XML과 이름이 다름

**원인:**
- 매핑 테이블: `ifrs-full_CurrentPortionOfLongTermBorrowings` (대문자 T)
- 실제 XML: `ifrs-full_CurrentPortionOfLongtermBorrowings` (소문자 t)
- XBRL 표준에서 일부 ACODE 이름의 대소문자가 다를 수 있음

**수정 파일:** `xbrl_acode_mappings.json`

**수정 내용:**
```json
"current_portion_of_long_term_borrowings": {
    "primary_acode": "ifrs-full:CurrentPortionOfLongTermBorrowings",
    "candidate_acodes": [
        "ifrs-full_CurrentPortionOfLongTermBorrowings",
        "ifrs-full_CurrentPortionOfLongtermBorrowings"  // 추가
    ],
    "description": "유동성장기차입금"
}
```

---

## 수정 결과

### 데이터 수집 성공 지표

**수정 전:**
- acode_index_size: 76개
- 모든 재무상태표 항목: 0

**수정 후:**
- acode_index_size: 133개 (57개 증가)
- 정상적으로 추출된 지표:
  - ✅ equity: 402,192,070,000,000 원
  - ✅ cash_and_cash_equivalents: 53,705,579,000,000 원
  - ✅ short_term_borrowings: 13,172,504,000,000 원
  - ✅ current_portion_of_long_term_borrowings: 2,207,290,000,000 원
  - ✅ long_term_borrowings: 3,935,860,000,000 원
  - ✅ bonds: 14,530,000,000 원
  - ✅ tangible_asset_acquisition: -51,406,355,000,000 원
  - ✅ intangible_asset_acquisition: -2,335,284,000,000 원
  - ✅ cfo: 72,982,621,000,000 원
  - ⚠️ lease_liabilities: 0 (XML에 해당 ACODE가 없음)

---

## 수정된 파일 목록

1. **apps/service/dart.py**
   - `collect_xbrl_indicators` 메서드에 YearlyFinancialData 자동 생성 로직 추가

2. **apps/service/xbrl_parser.py**
   - `filter_context` 메서드에서 `eFY` (ending Fiscal Year) 허용
   - 재무상태표 항목들이 필터링에서 제외되지 않도록 수정

3. **xbrl_acode_mappings.json**
   - `current_portion_of_long_term_borrowings`에 소문자 t 버전 ACODE 추가

---

## 디버깅 방법

### 1. 로깅 추가
- 함수 진입점, 중요한 변수 값, 예외 발생 시점에 로깅 추가
- NDJSON 형식으로 로그 파일에 저장하여 분석

### 2. 로그 분석
- `acode_index_size`, `matched_count`, `filtered_count` 등 통계 정보 확인
- 실제 XML 파일과 매핑 테이블의 ACODE 이름 비교
- `relevant_acodes_in_index`를 통해 실제 인덱스에 포함된 ACODE 확인

### 3. XML 파일 직접 확인
- 실제 XBRL XML 파일에서 ACONTEXT 패턴 확인
- `CFY2024eFY`, `CFY2024dFY` 등의 실제 사용 패턴 확인
- ACODE 이름의 실제 형식 확인 (대소문자, 언더스코어 등)

---

## 교훈

1. **예외 처리가 너무 넓으면 문제를 숨길 수 있음**
   - 예외를 조용히 처리하기 전에 로깅을 통해 원인을 파악해야 함

2. **XBRL 표준의 컨텍스트 타입을 정확히 이해해야 함**
   - `dFY` (duration) vs `eFY` (ending) 차이
   - 재무제표 유형별로 사용하는 컨텍스트가 다름

3. **매핑 테이블과 실제 데이터의 불일치 가능성**
   - ACODE 이름의 대소문자 차이
   - 후보 ACODE들을 충분히 포함해야 함

4. **디버깅 시 체계적인 접근**
   - 가설 설정 → 로깅 추가 → 데이터 분석 → 수정 → 검증의 단계적 프로세스

---

## 참고 자료

- XBRL 표준: IFRS Taxonomy
- DART API: 전자공시시스템 XBRL 파일 구조
- 파일 위치:
  - 코드: `apps/service/dart.py`, `apps/service/xbrl_parser.py`
  - 매핑 테이블: `xbrl_acode_mappings.json`
  - 테스트: `test_xbrl_collection.py`

