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

_PROMPT = """다음은 연결 재무상태표와 연결 현금흐름표에서 파싱한 rows JSON입니다.
각 row는 label(계정명)과 연도별 금액(2024, 2023, 2022 등)을 가집니다.

아래 6개 필드에 해당하는 label을 찾아 연도별 값을 추출해주세요. (정확한 label명 일치 또는 유사 표현)

필드별 매핑:
- cfo: 영업활동현금흐름
- tangible_asset_acquisition: 유형자산의취득, 유형자산취득 (투자활동, 음수면 절대값)
- intangible_asset_acquisition: 무형자산의취득, 무형자산취득 (투자활동, 음수면 절대값)
- cash_and_cash_equivalents: 기말현금및현금성자산 (현금흐름표 마지막 부근)
- interest_expense: 이자비용, 이자지급, 이자지급(영업) (음수면 절대값)
- interest_bearing_debt: 이자부채 계정들의 합계

규칙: 금액은 정수, 양수로. 없으면 0. interest_bearing_debt_labels에 이자부채 합산에 사용한 label 목록을 배열로.

반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{"2024": {"cfo": 0, "tangible_asset_acquisition": 0, "intangible_asset_acquisition": 0, "cash_and_cash_equivalents": 0, "interest_expense": 0, "interest_bearing_debt": 0}, "2023": {...}, "2022": {...}, "interest_bearing_debt_labels": []}

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
    prompt = _PROMPT + rows_json

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
        result[year] = row

    return result
