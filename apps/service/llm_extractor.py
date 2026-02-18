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
    "dividend_paid",  # 배당금 지급
]

def _build_prompt(years: list[int]) -> str:
    """연도 리스트에 맞춰 프롬프트와 응답 형식 예시를 동적으로 생성."""
    years_str = ", ".join(str(y) for y in years)
    year_blocks = ", ".join(
        f'"{y}": {{"cfo": 0, "tangible_asset_acquisition": 0, "intangible_asset_acquisition": 0, "cash_and_cash_equivalents": 0, "interest_expense": 0, "interest_bearing_debt": 0, "dividend_paid": 0}}'
        for y in years
    )
    breakdown_blocks = ", ".join(f'"{y}": {{}}' for y in years)
    first_year = years[0] if years else 2024
    return f"""다음은 연결 재무상태표와 연결 현금흐름표에서 파싱한 rows JSON입니다.
각 row는 label(계정명)과 연도별 금액({years_str})을 가집니다.

아래 7개 필드에 해당하는 label을 찾아 연도별 값을 추출해주세요. (정확한 label명 일치 또는 유사 표현)

## 필드별 지표 가이드

1. cfo (영업활동현금흐름) [중요: 부호 유지]
   - 현금흐름표: "영업활동현금흐름" 또는 "영업활동으로 인한 현금흐름" 계정(표 하단 합계 행).
   - rows에 금액이 음수(유출)로 되어 있으면 반드시 음수 그대로 넣고, 양수(유입)면 양수 그대로 넣으세요. 절대 절대값으로 바꾸지 마세요.
   - 예: rows에 "2024": -39859428111 이면 cfo에는 -39859428111 (음수 유지).

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
   - 재무상태표(부채)에서 이자부담이 있는 차입금·사채·리스부채 계정을 찾아, 연도별 금액을 interest_bearing_debt_breakdown에 넣으세요.
   - interest_bearing_debt_breakdown: 연도별 {{계정명: 금액}} 객체. rows에 나온 계정명(label)을 키로, 해당 금액(정수)을 값으로 넣으세요. 없으면 0.
   - interest_bearing_debt_labels: breakdown에 사용한 label 목록을 배열로.
   - 각 연도 블록의 interest_bearing_debt 필드는 0으로 두어도 됨 (코드에서 breakdown 합으로 계산함).

7. dividend_paid (배당금 지급)
   - 현금흐름표의 재무활동으로 인한 현금흐름에서 "배당금의 지급", "주주에게 배당금 지급" 등 해당 label을 찾아 연도별 금액 추출.
   - 금액이 음수(유출)로 나오면 절대값으로 저장.

## 규칙
- 금액은 정수, 없으면 0.
- interest_bearing_debt_breakdown이 핵심입니다. 연도별로 계정명→금액을 정확히 채우세요.

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이). 연도 키는 반드시 {years_str} 를 사용하세요:
{{{year_blocks}, "interest_bearing_debt_labels": [], "interest_bearing_debt_breakdown": {{{breakdown_blocks}}}}}

rows:
"""


def _sum_breakdown(breakdown: dict) -> int:
    """이자부채 breakdown(계정명→금액)의 금액 합계. LLM 총합 대신 사용."""
    total = 0
    for v in breakdown.values():
        if v is None:
            continue
        try:
            total += int(v)
        except (TypeError, ValueError):
            continue
    return total


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

    model = getattr(settings, "OPENAI_MODEL", "gpt-4o")
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
        # 이자부채는 LLM 총합 대신 breakdown 합으로 덮어써서 합산 오류 방지
        if breakdown_for_year:
            row["interest_bearing_debt"] = _sum_breakdown(breakdown_for_year)
        result[year] = row

    _log_extracted_indicators(result)
    return result


def _log_extracted_indicators(result: dict) -> None:
    """추출된 지표를 보기 쉽게 로그 출력."""
    if not result:
        return
    lines = ["", "[llm_extractor] 추출 지표"]
    field_labels = {
        "cfo": "영업활동현금흐름",
        "tangible_asset_acquisition": "유형자산취득",
        "intangible_asset_acquisition": "무형자산취득",
        "cash_and_cash_equivalents": "기말현금",
        "interest_expense": "이자비용",
        "interest_bearing_debt": "이자부채",
        "dividend_paid": "배당금지급",
    }
    for year in sorted(result.keys(), reverse=True):
        row = result[year]
        lines.append(f"  [{year}]")
        for f in _EXTRACT_FIELDS:
            val = row.get(f, 0)
            label = field_labels.get(f, f)
            lines.append(f"    {label}: {val:,}" if isinstance(val, int) else f"    {label}: {val}")
        bd = row.get("_interest_bearing_debt_breakdown") or {}
        if bd:
            lines.append("    이자부채(breakdown):")
            for k, v in sorted(bd.items(), key=lambda x: x[0]):
                lines.append(f"      {k}: {v:,}" if isinstance(v, int) else f"      {k}: {v}")
        lines.append("")
    logger.info("\n".join(lines))
