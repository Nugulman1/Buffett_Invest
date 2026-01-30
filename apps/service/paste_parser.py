"""
복붙 재무제표 파서

사업보고서에서 복사한 연결 재무상태표/현금흐름표 텍스트를 파싱하여
FCF/ROIC/WACC 계산에 필요한 계정 값을 추출합니다.
계정 매핑은 차차 추가해 나갑니다.
"""
import re
from apps.utils import normalize_account_name


# 계정 매핑: (표시명 변형 목록, 내부 필드명)
# 정규화 함수로 매칭하므로 표시명은 정규화 후 비교됩니다.
BALANCE_SHEET_MAPPING = [
    (["현금및현금성자산"], "cash_and_cash_equivalents"),
    (["단기차입금"], "short_term_borrowings"),
    (["유동성장기부채"], "current_portion_of_long_term_debt"),
    (["유동 리스부채", "유동리스부채"], "current_lease_liabilities"),
    (["장기차입금"], "long_term_borrowings"),
    (["비유동 리스부채", "비유동리스부채"], "non_current_lease_liabilities"),
]

CASH_FLOW_MAPPING = [
    (["영업활동현금흐름"], "cfo"),
    (["유형자산의 취득"], "tangible_asset_acquisition"),
    (["무형자산의 취득"], "intangible_asset_acquisition"),
    (["이자의 지급"], "interest_expense"),
]


def _build_normalized_mapping(mapping_list):
    """(표시명 목록, 필드명) 리스트 -> 정규화된 표시명 -> 필드명 딕셔너리"""
    result = {}
    for display_names, field in mapping_list:
        for name in display_names:
            key = normalize_account_name(name)
            if key not in result:
                result[key] = field
    return result


def _strip_footnote(label: str) -> str:
    """괄호 주석 (주5,6,7) 등 제거"""
    return re.sub(r"\s*\(주[^)]*\)\s*", "", label).strip()


def _normalize_amount_token(s: str) -> str:
    """전각 숫자/쉼표를 반각으로 변환 (PDF·DART 복사 시 전각으로 붙여넣어지는 경우 대비)."""
    if not s:
        return s
    # 전각 숫자 ０-９ (U+FF10–U+FF19) → 반각
    for i, c in enumerate("０１２３４５６７８９"):
        s = s.replace(c, str(i))
    # 전각 쉼표 ， (U+FF0C) → 반각
    s = s.replace("，", ",")
    return s


def _looks_like_amount(token: str) -> bool:
    """토큰이 금액(숫자, 쉼표, 괄호) 형태인지 판별"""
    t = _normalize_amount_token(token.strip()).replace(",", "").replace(" ", "")
    if not t:
        return False
    if t.startswith("(") and t.endswith(")"):
        t = t[1:-1]
    return t.isdigit() or (t.startswith("-") and t[1:].isdigit())


def _extract_label_before_numbers(line: str) -> str:
    """줄에서 첫 금액 컬럼 이전의 라벨 부분만 반환"""
    stripped = line.strip()
    tokens = re.split(r"[\s　]+", stripped)
    label_parts = []
    for t in tokens:
        if _looks_like_amount(t):
            break
        label_parts.append(t)
    return " ".join(label_parts).strip()


def _parse_amount_cell(cell: str) -> int:
    """쉼표 구분 숫자 또는 (123) 형태를 정수로. 빈 칸/공백은 0. 전각 숫자 지원."""
    cell = _normalize_amount_token((cell or "").strip()).replace(",", "").replace(" ", "").replace("　", "")
    if not cell:
        return 0
    if cell.startswith("(") and cell.endswith(")"):
        return -abs(int(cell[1:-1]))
    try:
        return int(cell)
    except ValueError:
        return 0


def _extract_amounts_from_line(line: str, max_columns: int = 3) -> list[int]:
    """한 줄에서 금액 컬럼들 추출 (당기/전기/전전기 순). 탭 구분 컬럼 지원."""
    tokens = re.split(r"[\s　\t]+", line.strip())
    amounts = []
    for t in tokens:
        if _looks_like_amount(t):
            amounts.append(_parse_amount_cell(t))
            if len(amounts) >= max_columns:
                break
    while len(amounts) < max_columns:
        amounts.append(0)
    return amounts[:max_columns]


def _extract_years_from_text(text: str) -> list[int]:
    """
    텍스트에서 '제 N 기 YYYY.MM.DD' 형태를 찾아 연도(YYYY) 리스트 반환.
    중복 제거, 순서 유지.
    """
    # 제 23 기 2024.12.31 현재 / 제 23 기 2024.01.01 부터 ...
    pattern = r"제\s*(\d+)\s*기\s*(\d{4})\.\d{1,2}\.\d{1,2}"
    seen = {}
    order = []
    for m in re.finditer(pattern, text):
        period, year_str = m.group(1), m.group(2)
        year = int(year_str)
        key = (year, period)
        if key not in seen:
            seen[key] = year
            order.append(year)
    if not order:
        # 대안: 2024.12.31 형태만 검색
        for m in re.finditer(r"20\d{2}\.\d{1,2}\.\d{1,2}", text):
            y = int(m.group()[:4])
            if y not in seen:
                seen[y] = y
                order.append(y)
    # 당기(최신) 먼저 오도록 내림차순
    order.sort(reverse=True)
    return order[:10]


def _parse_table_by_mapping(text: str, mapping_list: list, max_columns: int = 3) -> dict:
    """
    텍스트와 매핑을 받아 연도별 계정 값 딕셔너리 반환.

    Returns:
        {
            "years": [2024, 2023, 2022],
            "data": {
                2024: { "cfo": 60126008213, "cash_and_cash_equivalents": 86017437082, ... },
                2023: { ... },
                2022: { ... },
            }
        }
    """
    years = _extract_years_from_text(text)
    if not years:
        return {"years": [], "data": {}}

    normalized_map = _build_normalized_mapping(mapping_list)
    # 연도별로 채울 딕셔너리 (컬럼 순서 = years 순서)
    data_by_year = {y: {} for y in years}
    lines = text.splitlines()

    for idx, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue
        label_part = _extract_label_before_numbers(line_stripped)
        label_clean = _strip_footnote(label_part)
        label_normalized = normalize_account_name(label_clean)
        if not label_normalized:
            continue
        field = normalized_map.get(label_normalized)
        if not field:
            continue
        amounts = _extract_amounts_from_line(line_stripped, max_columns=max_columns)
        # 계정명만 있고 금액이 같은 줄에 없으면 다음 줄에서 금액 추출 (붙여넣기 형식: 계정 한 줄, 숫자 다음 줄)
        if not any(amounts) and idx + 1 < len(lines):
            next_line = lines[idx + 1].strip()
            if next_line:
                amounts = _extract_amounts_from_line(next_line, max_columns=max_columns)
        for i, year in enumerate(years):
            if i < len(amounts):
                data_by_year[year][field] = amounts[i]

    return {"years": years, "data": data_by_year}


def parse_balance_sheet(text: str) -> dict:
    """
    연결 재무상태표 텍스트 파싱.

    Returns:
        {"years": [2024, 2023, 2022], "data": { 2024: {...}, ... }}
    """
    return _parse_table_by_mapping(text, BALANCE_SHEET_MAPPING)


def parse_cash_flow(text: str) -> dict:
    """
    연결 현금흐름표 텍스트 파싱.

    유형/무형자산 취득은 보통 괄호로 음수 표기되므로 절댓값으로 저장 (capex 양수).
    이자의 지급은 절댓값으로 저장.

    Returns:
        {"years": [2024, 2023, 2022], "data": { 2024: {...}, ... }}
    """
    raw = _parse_table_by_mapping(text, CASH_FLOW_MAPPING)
    for year, row in raw["data"].items():
        if "tangible_asset_acquisition" in row and row["tangible_asset_acquisition"] < 0:
            row["tangible_asset_acquisition"] = abs(row["tangible_asset_acquisition"])
        if "intangible_asset_acquisition" in row and row["intangible_asset_acquisition"] < 0:
            row["intangible_asset_acquisition"] = abs(row["intangible_asset_acquisition"])
        if "interest_expense" in row and row["interest_expense"] < 0:
            row["interest_expense"] = abs(row["interest_expense"])
    return raw


def merge_parsed_balance_and_cash_flow(bs_result: dict, cf_result: dict) -> dict:
    """
    재무상태표 파싱 결과와 현금흐름표 파싱 결과를 연도별로 병합.
    연도는 두 결과의 교집합 또는 BS/CF 중 하나라도 있는 연도 모두 사용.
    """
    years_bs = set(bs_result.get("years", []))
    years_cf = set(cf_result.get("years", []))
    years = sorted(years_bs | years_cf, reverse=True)
    data_bs = bs_result.get("data", {})
    data_cf = cf_result.get("data", {})
    merged = {}
    for y in years:
        merged[y] = {**(data_bs.get(y, {})), **(data_cf.get(y, {}))}
    return {"years": years, "data": merged}
