"""
DART 전체재무제표(fnlttSinglAcntAll) rows에서 ROIC/WACC 입력 지표 추출.

LLM 없이 account_id(IFRS 표준 택소노미) + account_nm 키워드로 8개 필드를 뽑는다.
출력 구조: {year: {cfo, ..., _interest_bearing_debt_breakdown}}.

매핑 근거는 실데이터(삼성·NAVER·신한지주) 대조로 확정. 조정 포인트는 상수로 분리:
- 이자비용 소스 우선순위(INTEREST_EXPENSE_ID_PRIORITY): CF 이자의지급 > 이자비용 > 금융비용.
- 리스부채 포함 여부(INCLUDE_LEASE_IN_DEBT): IFRS-16 부채성으로 기본 포함.
"""
import logging

logger = logging.getLogger(__name__)

# ── account_id 매핑 (sj_div 제한이 필요한 것은 _SJ에 명시) ──
CFO_IDS = {"ifrs-full_CashFlowsFromUsedInOperatingActivities"}
TANGIBLE_IDS = {"ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"}
INTANGIBLE_IDS = {"ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities"}
CASH_END_IDS = {"dart_CashAndCashEquivalentsAtEndOfPeriodCf"}
CASH_END_FALLBACK_BS_IDS = {"ifrs-full_CashAndCashEquivalents"}  # CF 기말현금 없을 때 BS 현금
DIVIDEND_IDS = {"ifrs-full_DividendsPaidClassifiedAsFinancingActivities"}
NCI_BS_IDS = {"ifrs-full_NoncontrollingInterests"}  # 반드시 BS만(손익표에도 동명 존재)

# 이자비용: 우선순위대로 처음 잡히는 값 사용
#  1) CF "이자의 지급"(실제 현금 이자, 비금융사 최선)
#  2) "이자비용"(금융사 손익 본문)
#  3) "금융비용"(환차손 등 포함 넓은 개념 — 최후 폴백, Rd 과대 위험)
INTEREST_EXPENSE_ID_PRIORITY = [
    "ifrs-full_InterestPaidClassifiedAsOperatingActivities",
    "ifrs-full_InterestExpense",
    "ifrs-full_FinanceCosts",
]

# 이자부채(BS): 표준 account_id + 비표준 계정 대비 account_nm 키워드.
#  삼성 단기차입금처럼 account_id가 '-표준계정코드 미사용-'인 경우가 있어 키워드 폴백 필수.
DEBT_BS_IDS = {
    "ifrs-full_ShorttermBorrowings",
    "ifrs-full_CurrentPortionOfLongtermBorrowings",          # 유동성장기부채
    "ifrs-full_CurrentBondsIssuedAndCurrentPortionOfNoncurrentBondsIssued",  # 유동성사채
    "ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued",    # 사채
    "ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived",  # 장기차입금
    "ifrs-full_LongtermBorrowings",
    "ifrs-full_BondsIssued",                                 # 금융사 사채
}
DEBT_LEASE_IDS = {
    "ifrs-full_CurrentLeaseLiabilities",
    "ifrs-full_NoncurrentLeaseLiabilities",
}
DEBT_NAME_KEYWORDS = ("차입금", "사채", "리스부채")
DEBT_LEASE_KEYWORDS = ("리스부채",)
INCLUDE_LEASE_IN_DEBT = True
# 키워드 폴백 시 제외할 소계/합계 표시자. '차입금및사채'(소계)가 leaf와 중복 가산되는
# 것을 막는다. 표준 account_id 경로에는 소계가 없으므로 키워드 폴백에만 적용.
DEBT_SUBTOTAL_BLOCK = ("및", "소계", "합계", "총계")

_EXTRACT_FIELDS = [
    "cfo", "tangible_asset_acquisition", "intangible_asset_acquisition",
    "cash_and_cash_equivalents", "interest_expense", "interest_bearing_debt",
    "dividend_paid", "noncontrolling_interest",
]
# 크기(magnitude)로 다루는 필드 — 음수면 절대값. cfo는 부호 유지.
_ABS_FIELDS = {"tangible_asset_acquisition", "intangible_asset_acquisition",
               "dividend_paid", "interest_expense"}

_AMOUNT_KEYS = ("thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount")  # 당기, 전기, 전전기


def _parse_amount(s) -> int | None:
    """'1,234' / '-1,234' / '' / '-' → int 또는 None."""
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if s in ("", "-"):
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _is_debt_row(row: dict) -> bool:
    if row.get("sj_div") != "BS":
        return False
    aid = row.get("account_id") or ""
    nm = row.get("account_nm") or ""
    if aid in DEBT_BS_IDS:
        return True
    if INCLUDE_LEASE_IN_DEBT and aid in DEBT_LEASE_IDS:
        return True
    # 키워드 폴백: 소계('차입금및사채' 등)는 leaf와 중복 가산되므로 제외
    if any(b in nm for b in DEBT_SUBTOTAL_BLOCK):
        return False
    keywords = DEBT_NAME_KEYWORDS if INCLUDE_LEASE_IN_DEBT else tuple(
        k for k in DEBT_NAME_KEYWORDS if k not in DEBT_LEASE_KEYWORDS
    )
    return any(k in nm for k in keywords)


def extract_financial_indicators_from_dart(rows: list[dict], bsns_year: int) -> dict[int, dict]:
    """
    fnlttSinglAcntAll 한 응답(rows)에서 3개년(bsns_year, -1, -2) 지표 추출.

    Args:
        rows: get_financial_statement_all() 반환 리스트
        bsns_year: 당기 사업연도(정수). thstrm=bsns_year, frmtrm=-1, bfefrmtrm=-2

    Returns:
        {year: {cfo, tangible_asset_acquisition, ..., _interest_bearing_debt_breakdown}}
    """
    years = [bsns_year, bsns_year - 1, bsns_year - 2]
    # year -> {field: value}
    result = {y: {f: 0 for f in _EXTRACT_FIELDS} for y in years}
    for y in years:
        result[y]["_interest_bearing_debt_breakdown"] = {}

    # 이자비용은 우선순위가 높은 소스를 이미 잡았는지 추적(연도별)
    interest_locked = {y: None for y in years}  # 잡힌 소스의 우선순위 인덱스

    for row in rows:
        aid = row.get("account_id") or ""
        sj = row.get("sj_div")
        nm = row.get("account_nm") or ""
        amounts = {y: _parse_amount(row.get(k)) for y, k in zip(years, _AMOUNT_KEYS)}

        def add(field, *, absolute=False):
            for y in years:
                v = amounts[y]
                if v is None:
                    continue
                result[y][field] = abs(v) if absolute else v

        if aid in CFO_IDS:
            add("cfo")
        elif aid in TANGIBLE_IDS:
            add("tangible_asset_acquisition", absolute=True)
        elif aid in INTANGIBLE_IDS:
            add("intangible_asset_acquisition", absolute=True)
        elif aid in CASH_END_IDS:
            add("cash_and_cash_equivalents")
        elif aid in DIVIDEND_IDS:
            add("dividend_paid", absolute=True)
        elif aid in NCI_BS_IDS and sj == "BS":
            add("noncontrolling_interest")

        # 이자비용: 우선순위 비교(낮은 인덱스가 우선)
        if aid in INTEREST_EXPENSE_ID_PRIORITY:
            prio = INTEREST_EXPENSE_ID_PRIORITY.index(aid)
            for y in years:
                v = amounts[y]
                if v is None:
                    continue
                cur = interest_locked[y]
                if cur is None or prio < cur:
                    result[y]["interest_expense"] = abs(v)
                    interest_locked[y] = prio

        # 이자부채: 행별 누적 합 + breakdown
        if _is_debt_row(row):
            for y in years:
                v = amounts[y]
                if v is None or v == 0:
                    continue
                # 부호 유지: contra 계정(사채할인발행차금 등 음수)은 자연히 차감된다.
                # abs로 더하면 차감계정이 가산돼 과대집계됨.
                result[y]["interest_bearing_debt"] += v
                bd = result[y]["_interest_bearing_debt_breakdown"]
                # 동일 계정명(예: 리스부채 유동/비유동)이 여러 줄이면 누적
                bd[nm] = bd.get(nm, 0) + v

    # CF 기말현금 폴백(BS 현금) — CF에서 못 잡은 연도만
    for row in rows:
        if (row.get("account_id") or "") in CASH_END_FALLBACK_BS_IDS and row.get("sj_div") == "BS":
            amounts = {y: _parse_amount(row.get(k)) for y, k in zip(years, _AMOUNT_KEYS)}
            for y in years:
                if result[y]["cash_and_cash_equivalents"] == 0 and amounts[y] is not None:
                    result[y]["cash_and_cash_equivalents"] = amounts[y]

    _log_extracted(result, bsns_year)
    return result


def _log_extracted(result: dict, bsns_year: int) -> None:
    labels = {
        "cfo": "영업현금흐름", "tangible_asset_acquisition": "유형취득",
        "intangible_asset_acquisition": "무형취득", "cash_and_cash_equivalents": "기말현금",
        "interest_expense": "이자비용", "interest_bearing_debt": "이자부채",
        "dividend_paid": "배당금지급", "noncontrolling_interest": "비지배지분",
    }
    lines = ["", f"[dart_extractor] 추출 지표 (기준연도 {bsns_year})"]
    for y in sorted(result.keys(), reverse=True):
        row = result[y]
        lines.append(f"  [{y}]")
        for f in _EXTRACT_FIELDS:
            lines.append(f"    {labels[f]}: {row[f]:,}")
        bd = row.get("_interest_bearing_debt_breakdown") or {}
        if bd:
            lines.append("    이자부채(breakdown):")
            for k, v in bd.items():
                lines.append(f"      {k}: {v:,}")
    logger.debug("\n".join(lines))
