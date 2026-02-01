"""
복붙 재무제표 파서

사업보고서에서 복사한 연결 재무상태표/현금흐름표 텍스트를 파싱하여
FCF/ROIC/WACC 계산에 필요한 계정 값을 추출합니다.
연도 추출 + 표 본문 분리(자산/영업) + 한글(지표명)·숫자(금액) 분리 → rows JSON.
"""
import logging
import re

logger = logging.getLogger(__name__)

# 공백·쉼표 제거 후 금액: 숫자만 또는 (숫자)
_AMOUNT_RE = re.compile(r"^(\d+|\(\d+\))$")


def _is_amount_token(s: str) -> bool:
    """공백·쉼표 제거된 문자열이 금액(숫자만 또는 (숫자))이면 True."""
    return bool(s and _AMOUNT_RE.match(s.strip()))


def _parse_amount(s: str) -> int | None:
    """금액 문자열을 정수로. (숫자)면 음수. 비금액이면 None."""
    if not s:
        return None
    t = s.strip()
    if not _AMOUNT_RE.match(t):
        return None
    neg = t.startswith("(") and t.endswith(")")
    num_str = t.strip("()")
    return -int(num_str) if neg else int(num_str)


def _normalize_label(s: str) -> str:
    """지표명 앞뒤 공백·전각 공백 제거."""
    return s.replace("\u3000", " ").strip()


def _is_whitespace_only(s: str) -> bool:
    """줄이 공백·전각 공백만 있으면 True (빈 칸 자리 보존용)."""
    return not s or s.replace("\u3000", " ").strip() == ""


def _cells_from_trimmed(trimmed_text: str) -> list[str]:
    """
    표 본문을 줄 단위로 나눈 뒤, 각 줄을 셀으로 추가.
    공백만 있는 줄은 빈 셀 '' 로 넣어 연도 순서(자리)를 유지.
    내용 있는 줄은 공백·쉼표 제거한 문자열로 넣음.
    """
    cells = []
    for line in trimmed_text.splitlines():
        if _is_whitespace_only(line):
            cells.append("")
        else:
            cells.append(re.sub(r"[\s\u3000,]+", "", line))
    return cells


def _row_cells_to_slots(row_cells: list[str], empty_value: int | str | None) -> list:
    """
    숫자 값 개수 + 연속 공백 수로 [2024, 2023, 2022] 슬롯 매핑.
    - 3개: 순서대로 [V1, V2, V3].
    - 2개: 연속 공백(2개 이상)이 나오는 연도 = null, 나머지에 값 순서대로.
    - 1개: 앞에 연속 공백 2개 이상 → 2022, 뒤에 2개 이상 → 2024, 나머지(앞뒤 각 2개) → 2023.
    """
    n = len(row_cells)
    if n == 0:
        return [empty_value, empty_value, empty_value]

    values = []
    value_indices = []
    for i, c in enumerate(row_cells):
        if c != "" and _is_amount_token(c):
            values.append(_parse_amount(c))
            value_indices.append(i)

    num_values = len(values)
    if num_values == 0:
        return [empty_value, empty_value, empty_value]

    if num_values == 3:
        return [values[0], values[1], values[2]]

    if num_values == 2:
        # 연속 공백(2개 이상)이 나오는 위치 → 해당 연도 null
        i0, i1 = value_indices[0], value_indices[1]
        leading = i0
        middle = i1 - i0 - 1
        trailing = n - i1 - 1
        if leading >= 2:
            return [empty_value, values[0], values[1]]
        if middle >= 2:
            return [values[0], empty_value, values[1]]
        if trailing >= 2:
            return [values[0], values[1], empty_value]
        return [values[0], values[1], empty_value]

    # num_values == 1
    idx = value_indices[0]
    leading = idx
    trailing = n - idx - 1
    if leading >= 2 and trailing < 2:
        return [empty_value, empty_value, values[0]]
    if trailing >= 2 and leading < 2:
        return [values[0], empty_value, empty_value]
    return [empty_value, values[0], empty_value]


def parse_table_body_to_rows(
    trimmed_text: str,
    years: list[int],
    empty_value: int | str | None = 0,
    unit_multiplier: int = 1,
) -> list[dict]:
    """
    표 본문(trimmed)을 한글(지표명)·숫자(금액)로 분리해 행 단위 JSON 리스트 반환.
    라벨 다음 셀들을 한 행으로 모은 뒤, 길이에 따라 3개 연도 슬롯으로 매핑.
    (값 사이 빈 줄=구분자 6개 → 1,3,5가 값 / 빈 칸 포함 4개 → 0,1,3 등)
    빈 값은 empty_value. 기본 0, None이면 null.
    unit_multiplier: 금액을 원 단위로 변환할 배수 (천원=1000, 백만원=1000000).
    """
    cells = _cells_from_trimmed(trimmed_text)
    rows = []
    i = 0
    while i < len(cells):
        cell = cells[i]
        if cell == "" or _is_amount_token(cell):
            i += 1
            continue
        label = _normalize_label(cell)
        j = i + 1
        row_cells = []
        while j < len(cells):
            c = cells[j]
            if c != "" and not _is_amount_token(c):
                break
            row_cells.append(c)
            j += 1
        values = _row_cells_to_slots(row_cells, empty_value)
        row = {"label": label}
        for idx, y in enumerate(years):
            val = values[idx] if idx < len(values) else empty_value
            if isinstance(val, int):
                row[y] = val * unit_multiplier
            else:
                row[y] = val
        rows.append(row)
        i = j
    logger.info("[paste_parser] parse_table_body_to_rows: %s rows", len(rows))
    return rows


def _extract_years_from_text(text: str) -> list[int]:
    """
    텍스트에서 처음 나오는 2020~2029 연도를 당기로 하고,
    [당기, 전기, 전전기] 3개 반환.
    """
    m = re.search(r"202[0-9]", text)
    if not m:
        logger.error("[paste_parser] 연도 추출 실패: 텍스트에 2020~2029 형식이 없음")
        raise ValueError(
            "연도를 찾을 수 없습니다. 텍스트에 2020~2029 형식이 있는지 확인해주세요."
        )
    report_year = int(m.group())
    years = [report_year, report_year - 1, report_year - 2]
    logger.info("[paste_parser] 연도 추출: 첫 202X=%s -> years=%s", report_year, years)
    return years


def _extract_unit_from_text(text: str) -> int:
    """
    텍스트에서 처음 나오는 '단위' 문자열을 찾아 원 단위 배수 반환.
    원→1, 천원→1_000, 백만원→1_000_000. 못 찾으면 1.
    """
    m = re.search(r"단위\s*:\s*([^),]+)", text)
    if not m:
        logger.warning("[paste_parser] 단위 추출 실패: '단위'를 찾을 수 없음 -> 1(원)으로 처리")
        return 1
    unit_str = m.group(1).strip().replace(" ", "")
    if "백만원" in unit_str:
        return 1_000_000
    if "천원" in unit_str:
        return 1_000
    if "원" in unit_str:
        return 1
    logger.warning("[paste_parser] 알 수 없는 단위 %r -> 1(원)으로 처리", unit_str)
    return 1


def _trim_from_first_marker(
    text: str, marker: str, exact_line: bool = True, contains: bool = False
) -> str:
    """
    텍스트에서 첫 번째 마커가 나오는 줄부터 끝까지 반환.
    재무상태표: marker='자산', exact_line=True (줄 전체가 '자산'인 경우만)
    현금흐름표: marker='영업', contains=True (줄에 '영업'이 포함되면, 표기 변형 대응)
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        # 전각 공백(\u3000)도 일반 공백으로 정규화 후 비교
        stripped = line.replace("\u3000", " ").strip()
        if exact_line:
            if stripped == marker:
                result = "\n".join(lines[i:])
                logger.info("[paste_parser] _trim_from_first_marker: marker=%r, exact_line=True, 시작 줄=%s", marker, i + 1)
                return result
        elif contains:
            if marker in stripped:
                result = "\n".join(lines[i:])
                logger.info("[paste_parser] _trim_from_first_marker: marker=%r, contains=True, 시작 줄=%s", marker, i + 1)
                return result
        else:
            if stripped.startswith(marker):
                result = "\n".join(lines[i:])
                logger.info("[paste_parser] _trim_from_first_marker: marker=%r, startswith, 시작 줄=%s", marker, i + 1)
                return result
    logger.error("[paste_parser] _trim_from_first_marker: 마커 %r 를 찾을 수 없음", marker)
    raise ValueError(f"표 시작을 찾을 수 없습니다. '{marker}' 가 있는지 확인해주세요.")


def parse_balance_sheet(text: str) -> dict:
    """
    연결 재무상태표 텍스트: 연도 추출 + '자산' 줄부터 표 본문 분리 + rows(지표명·금액 JSON).
    반환: {"years": [...], "data": {연도: {}}, "rows": [{"label": ..., 연도: 값}, ...]}
    """
    years = _extract_years_from_text(text)
    unit_multiplier = _extract_unit_from_text(text)
    trimmed = _trim_from_first_marker(text, "자산", exact_line=True)
    rows = parse_table_body_to_rows(trimmed, years, unit_multiplier=unit_multiplier)
    logger.info("[paste_parser] parse_balance_sheet: years=%s, rows=%s", years, len(rows))
    return {"years": years, "data": {y: {} for y in years}, "rows": rows}


def parse_cash_flow(text: str) -> dict:
    """
    연결 현금흐름표 텍스트: 연도 추출 + '영업' 포함 첫 줄부터 표 본문 분리 + rows(지표명·금액 JSON).
    반환: {"years": [...], "data": {연도: {}}, "rows": [{"label": ..., 연도: 값}, ...]}
    """
    years = _extract_years_from_text(text)
    unit_multiplier = _extract_unit_from_text(text)
    trimmed = _trim_from_first_marker(text, "영업", exact_line=False, contains=True)
    rows = parse_table_body_to_rows(trimmed, years, unit_multiplier=unit_multiplier)
    logger.info("[paste_parser] parse_cash_flow: years=%s, rows=%s", years, len(rows))
    return {"years": years, "data": {y: {} for y in years}, "rows": rows}
