# 디버깅 세션 문서

이 문서는 XBRL 파싱 기능 구현 중 발생한 두 가지 주요 이슈의 디버깅 과정을 기록합니다.

## 이슈 1: 사업보고서 접수번호 찾기 실패

### 문제 상황
- `get_annual_report_rcept_no` 메서드에서 사업보고서 접수번호를 찾지 못함
- 에러 메시지: "경고: 2024년 사업보고서 접수번호를 찾을 수 없습니다."

### 원인 분석

디버깅 과정에서 다음 문제들을 발견했습니다:

1. **페이지네이션 문제**
   - `get_report_list` API가 기본적으로 `page_count=10`으로 제한되어 있음
   - 사업보고서가 포함된 페이지를 놓치고 있었음
   - API 응답에 `total_page` 정보가 있지만 활용하지 않음

2. **검색 기간 설정 오류**
   - 연간보고서는 사업연도 다음 해에 발행됨 (예: 2024년 사업보고서는 2025년 3-4월 제출)
   - 초기에는 잘못된 기간으로 검색하고 있었음

3. **보고서 필터링 문제**
   - `last_reprt_at='Y'`로 설정하여 최종보고서만 조회
   - 사업보고서가 최종보고서가 아닐 수 있음

### 해결 과정

#### 1단계: 페이지네이션 지원 추가
- `get_report_list` 메서드에 `page_no`, `page_count` 파라미터 추가
- API 응답에서 `total_page`, `total_count` 정보를 반환하도록 수정
- `page_count` 최대값을 1000으로 설정

```python
def get_report_list(self, corp_code, bgn_de, end_de, last_reprt_at='N', page_no=1, page_count=1000):
    # ...
    return {
        'list': result.get('list', []),
        'total_page': result.get('total_page', 1),
        'total_count': result.get('total_count', 0)
    }
```

#### 2단계: 모든 페이지 순회 로직 구현
- `get_annual_report_rcept_no`에서 `total_page`를 확인하여 모든 페이지를 순회
- `page_count=1000`으로 설정하여 최대한 많은 보고서를 한 번에 조회

```python
all_reports = []
page_no = 1
total_page = 1
while True:
    result = self.get_report_list(corp_code, bgn_de, end_de, last_reprt_at='N', page_no=page_no, page_count=1000)
    report_list = result.get('list', []) if isinstance(result, dict) else []
    total_page = result.get('total_page', 1) if isinstance(result, dict) else 1
    
    if not report_list:
        break
    all_reports.extend(report_list)
    if page_no >= total_page:
        break
    page_no += 1
```

#### 3단계: 검색 기간 수정
- 사업보고서는 다음 해 3월~4월에 제출되므로 검색 기간을 해당 기간으로 제한
- `bgn_de = f"{next_year}0301"` (다음 해 3월 1일)
- `end_de = f"{next_year}0430"` (다음 해 4월 30일)

#### 4단계: 보고서 필터링 개선
- `last_reprt_at='N'`으로 변경하여 모든 보고서 조회
- `report_nm`에 "사업보고서"가 포함된 보고서만 필터링
- 접수번호의 연도가 다음 해와 일치하는지 확인

### 최종 해결 방법

**수정된 파일**: `apps/dart/client.py`

1. `get_report_list` 메서드:
   - `page_no`, `page_count` 파라미터 추가
   - `total_page`, `total_count` 반환

2. `get_annual_report_rcept_no` 메서드:
   - 페이지네이션 루프 구현
   - 검색 기간을 다음 해 3월 1일 ~ 4월 30일로 설정
   - `last_reprt_at='N'`으로 모든 보고서 조회
   - `report_nm`에 "사업보고서" 포함 여부로 필터링

### 결과
- 모든 페이지를 순회하여 사업보고서를 찾을 수 있게 됨
- 검색 기간 최적화로 불필요한 API 호출 감소
- 사업보고서 접수번호를 정확히 찾을 수 있게 됨

---

## 이슈 2: XML 파싱 실패 (not well-formed)

### 문제 상황
- `ET.fromstring()`이 "not well-formed (invalid token): line 277, column 20" 오류 발생
- XML 파일을 파싱할 수 없어 XBRL 데이터 추출 실패

### 원인 분석

1. **XML 형식 문제**
   - XBRL XML 파일이 표준 XML 파서가 처리하기 어려운 형식
   - 일부 특수 문자나 인코딩 문제로 인해 파싱 실패
   - XML 파일이 매우 크고 복잡한 구조

2. **파싱 방법의 한계**
   - `ET.fromstring()`은 완전히 유효한 XML만 파싱 가능
   - Incremental parser도 동일한 오류 발생

### 해결 과정

#### 1단계: 문자열 검색 우선 전략
- XML 파싱 전에 문자열 검색으로 `DOCUMENT-NAME`과 `ACODE="11011"`을 먼저 확인
- 문자열 검색으로 찾았으면 XML 파싱 실패해도 반환

```python
# XML 파싱 전에 문자열 검색으로 먼저 확인
xml_str = xml_content.decode('utf-8', errors='ignore')
if 'DOCUMENT-NAME' in xml_str and 'ACODE="11011"' in xml_str:
    # XML 파싱 시도
    try:
        root = ET.fromstring(xml_content)
        # ...
    except (ET.ParseError, ExpatError, UnicodeDecodeError) as e:
        # 파싱 실패해도 문자열 검색으로 찾았으므로 반환
        return xml_content
```

#### 2단계: 정규식 기반 파싱 추가
- XML 파싱이 실패할 경우를 대비하여 정규식 기반 파싱 메서드 추가
- `build_acode_index_from_regex` 메서드 구현
- TE 태그에서 ACODE, ACONTEXT, ADECIMAL, 값 추출

```python
def build_acode_index_from_regex(self, xml_str: str) -> dict:
    acode_index = {}
    te_pattern = r'<TE([^>]*)>(.*?)</TE>'
    
    for match in re.finditer(te_pattern, xml_str, re.DOTALL):
        attrs_str = match.group(1)
        content = match.group(2)
        
        # ACODE, ACONTEXT, ADECIMAL 추출
        acode_match = re.search(r'ACODE="([^"]+)"', attrs_str)
        # ...
        
        # 값 추출: P 태그가 있으면 P 태그 안의 값, 없으면 직접 텍스트
        p_match = re.search(r'<P[^>]*>([^<]+)</P>', content)
        if p_match:
            value_str = p_match.group(1).strip()
        else:
            value_str = re.sub(r'<[^>]+>', '', content).strip()
        
        # ...
```

#### 3단계: 폴백 메커니즘 구현
- `parse_xbrl_file`에서 XML 파싱 실패 시 정규식 파싱으로 자동 전환
- 여러 단계의 파싱 시도:
  1. `ET.fromstring()` 시도
  2. Incremental parser 시도
  3. 정규식 파싱으로 폴백

```python
def parse_xbrl_file(self, xml_content: bytes) -> dict:
    try:
        root = ET.fromstring(xml_content)
        acode_index = self.build_acode_index(root)
    except ET.ParseError as e1:
        try:
            # Incremental parser 시도
            parser = ET.XMLParser()
            parser.feed(xml_content)
            root = parser.close()
            acode_index = self.build_acode_index(root)
        except Exception as e2:
            # 정규식 파싱으로 폴백
            xml_str = xml_content.decode('utf-8', errors='ignore')
            acode_index = self.build_acode_index_from_regex(xml_str)
    
    # ACODE 인덱스에서 데이터 추출
    # ...
```

### 최종 해결 방법

**수정된 파일**: `apps/service/xbrl_parser.py`

1. `extract_annual_report_file` 메서드:
   - 문자열 검색 우선 전략 적용
   - XML 파싱 실패해도 문자열 검색으로 찾았으면 반환

2. `build_acode_index_from_regex` 메서드 (신규):
   - 정규식으로 TE 태그 파싱
   - ACODE, ACONTEXT, ADECIMAL, 값 추출
   - P 태그 내부 값 또는 직접 텍스트 값 모두 처리

3. `parse_xbrl_file` 메서드:
   - XML 파싱 실패 시 정규식 파싱으로 자동 전환
   - 여러 단계의 폴백 메커니즘 구현

### 결과
- XML 파싱이 실패해도 정규식 파싱으로 데이터 추출 가능
- 디버깅 로그에서 확인된 결과:
  - 정규식 파싱으로 16,149개의 TE 태그 발견
  - 필터링 후 232개 매칭, 76개의 ACODE 인덱스 생성
  - 유형자산 취득, 무형자산 취득, CFO 데이터 성공적으로 추출

### 디버깅 로그 요약

```
regex parsing started: xml_str_length=5780877
regex parsing completed: te_tags_found=16149, matched_after_filter=232, acode_index_size=76
extracted indicator: tangible_asset_acquisition=-51406355000000
extracted indicator: intangible_asset_acquisition=-2335284000000
extracted indicator: cfo=72982621000000
```

---

## 교훈 및 개선 사항

### 1. API 페이지네이션 처리
- API 응답의 `total_page` 정보를 항상 확인
- 모든 페이지를 순회하는 로직 구현 필요

### 2. XML 파싱의 한계
- 표준 XML 파서가 실패할 수 있으므로 대체 방법 준비
- 정규식 파싱은 유효하지 않은 XML도 처리 가능하지만, 성능과 정확도 면에서 제한적
- 가능하면 XML 파싱을 우선 시도하고, 실패 시에만 정규식 사용

### 3. 에러 처리 전략
- 여러 단계의 폴백 메커니즘 구현
- 문자열 검색으로 사전 확인하여 불필요한 파싱 시도 방지

### 4. 디버깅 도구 활용
- 상세한 로깅으로 문제 원인 파악
- 각 단계별 상태를 로그로 기록하여 디버깅 효율성 향상

