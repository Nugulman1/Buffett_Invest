"""
LLM을 활용한 재무제표 rows에서 지표 추출

FCF/ROIC/WACC 계산에 필요한 필드를 rows JSON에서 추출합니다.
"""
import json
import logging
from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)

_EXTRACT_FIELDS = [
    "cfo",  # 영업활동현금흐름
    "tangible_asset_acquisition",  # 유형자산 취득
    "intangible_asset_acquisition",  # 무형자산 취득
    "cash_and_cash_equivalents",  # 기말현금및현금성자산
    "interest_expense",  # 이자비용/이자지급
    "interest_bearing_debt",  # 이자부채
]

def _build_prompt(years: list[int]) -> str:
    """연도 리스트에 맞춰 프롬프트와 응답 형식 예시를 동적으로 생성."""
    years_str = ", ".join(str(y) for y in years)
    year_blocks = ", ".join(
        f'"{y}": {{"cfo": 0, "tangible_asset_acquisition": 0, "intangible_asset_acquisition": 0, "cash_and_cash_equivalents": 0, "interest_expense": 0, "interest_bearing_debt": 0}}'
        for y in years
    )
    breakdown_blocks = ", ".join(f'"{y}": {{}}' for y in years)
    first_year = years[0] if years else 2024
    return f"""다음은 연결 재무상태표와 연결 현금흐름표에서 파싱한 rows JSON입니다.
각 row는 label(계정명)과 연도별 금액({years_str})을 가집니다.

아래 6개 필드에 해당하는 label을 찾아 연도별 값을 추출해주세요. (정확한 label명 일치 또는 유사 표현)

## 필드별 지표 가이드

1. cfo (영업활동현금흐름)
   - 재무상태: 영업활동으로 인한 현금의 유입·유출 합계.
   - 현금흐름표: "영업활동으로 인한 현금흐름" 또는 "영업활동현금흐름" 계정. 보통 표 하단 합계 행.

2. tangible_asset_acquisition (유형자산 취득)
   - 투자활동에서 유형자산 구입에 지출한 현금. "유형자산의취득", "유형자산취득" 등.
   - 금액이 음수로 나오면 절대값으로 저장.

3. intangible_asset_acquisition (무형자산 취득)
   - 투자활동에서 무형자산 구입에 지출한 현금. "무형자산의취득", "무형자산취득" 등.
   - 금액이 음수로 나오면 절대값으로 저장.

4. cash_and_cash_equivalents (기말현금및현금성자산)
   - 현금흐름표 마지막에 나오는 "기말현금및현금성자산".

5. interest_expense (이자비용)
   - 손익계산서/포괄손익계산서의 "이자비용", "이자지급", "이자지급(영업)" 등.
   - 금액이 음수로 나오면 절대값으로 저장.

6. interest_bearing_debt (이자부채)
   - 재무상태표(부채)에서 이자부담이 있는 차입금·사채·리스부채의 합계.
   - 반드시 아래 5개 계정을 모두 찾아 합산하세요 (없는 계정은 0으로):
     * 단기차입금
     * 장기차입금
     * 유동성장기차입금 (당기 1년 이내 상환 구간)
     * 사채 (장기사채, 유동사채 등 사채 계정 전부)
     * 리스부채
   - interest_bearing_debt_labels에는 위 합산에 사용한 label 전체를 배열로 나열.
   - interest_bearing_debt_breakdown: 디버깅용. 연도별로 "어떤 계정명을 어떤 금액으로 가져왔는지" 객체. 예: {{"{first_year}": {{"단기차입금": 100, "장기차입금": 200}}, ...}}

## 규칙
- 금액은 정수, 양수로. 없으면 0.
- interest_bearing_debt_labels: 이자부채 합산에 사용한 label 목록을 배열로.
- interest_bearing_debt_breakdown: 연도별 {{계정명: 금액}} 객체 (디버깅용).

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이). 연도 키는 반드시 {years_str} 를 사용하세요:
{{{year_blocks}, "interest_bearing_debt_labels": [], "interest_bearing_debt_breakdown": {{{breakdown_blocks}}}}}

rows:
"""




def extract_financial_indicators(rows: list[dict], years: list[int]) -> dict[int, dict]:
    """
    rows JSON에서 FCF/ROIC/WACC 계산에 필요한 지표 추출.

    Args:
        rows: [{"label": "...", 2024: val, 2023: val, 2022: val}, ...]
        years: [2024, 2023, 2022]

    Returns:
        {2024: {cfo, tangible_asset_acquisition, ...}, 2023: {...}, 2022: {...}}
    """
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다. .env를 확인해주세요.")

    model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    rows_json = json.dumps(rows, ensure_ascii=False, indent=2)
    prompt = _build_prompt(years) + rows_json

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
    except json.JSONDecodeError as e:
        logger.exception("[llm_extractor] JSON 파싱 실패: %s", e)
        raise ValueError(f"LLM 응답 파싱 실패: {e}") from e
    except Exception as e:
        logger.exception("[llm_extractor] LLM 호출 실패: %s", e)
        raise

    result = {}
    interest_bearing_debt_labels = parsed.get("interest_bearing_debt_labels", [])
    if not isinstance(interest_bearing_debt_labels, list):
        interest_bearing_debt_labels = []

    interest_bearing_debt_breakdown = parsed.get("interest_bearing_debt_breakdown", {})
    if not isinstance(interest_bearing_debt_breakdown, dict):
        interest_bearing_debt_breakdown = {}

    for year in years:
        year_str = str(year)
        raw = parsed.get(year_str, {})
        if not isinstance(raw, dict):
            raw = {}
        row = {}
        for field in _EXTRACT_FIELDS:
            val = raw.get(field, 0)
            if val is None:
                val = 0
            try:
                row[field] = int(val)
            except (TypeError, ValueError):
                row[field] = 0
        row["_interest_bearing_debt_labels"] = interest_bearing_debt_labels
        breakdown_for_year = interest_bearing_debt_breakdown.get(year_str, {})
        if not isinstance(breakdown_for_year, dict):
            breakdown_for_year = {}
        row["_interest_bearing_debt_breakdown"] = breakdown_for_year
        result[year] = row

    return result
