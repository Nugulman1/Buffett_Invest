"""
dart_extractor 회귀 안전망 (T3).

합성 rows로 까다로운 케이스를 고정:
- 비표준 account_id('-표준계정코드 미사용-') 단기차입금은 키워드로 잡힘
- 이자비용 우선순위: 이자의지급(InterestPaid) > 금융비용(FinanceCosts)
- 비지배지분은 BS만(손익표 동명 계정 제외)
- 리스부채 유동/비유동 2줄 합산
- 유형/무형취득·배당·이자비용은 음수면 절대값, cfo는 부호 유지
- thstrm/frmtrm/bfefrmtrm → 3개년
"""
from apps.service.dart_extractor import extract_financial_indicators_from_dart


def row(sj, aid, nm, th, fr=None, bfe=None):
    return {
        "sj_div": sj, "account_id": aid, "account_nm": nm,
        "thstrm_amount": th, "frmtrm_amount": fr, "bfefrmtrm_amount": bfe,
    }


def _extract(rows, year=2023):
    return extract_financial_indicators_from_dart(rows, year)


class TestCoreMapping:
    def test_basic_fields(self):
        rows = [
            row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "1000"),
            row("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "유형자산의 취득", "300"),
            row("CF", "ifrs-full_PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities", "무형자산의 취득", "100"),
            row("CF", "dart_CashAndCashEquivalentsAtEndOfPeriodCf", "기말현금및현금성자산", "500"),
            row("CF", "ifrs-full_DividendsPaidClassifiedAsFinancingActivities", "배당금의 지급", "200"),
            row("BS", "ifrs-full_NoncontrollingInterests", "비지배지분", "50"),
        ]
        r = _extract(rows)[2023]
        assert r["cfo"] == 1000
        assert r["tangible_asset_acquisition"] == 300
        assert r["intangible_asset_acquisition"] == 100
        assert r["cash_and_cash_equivalents"] == 500
        assert r["dividend_paid"] == 200
        assert r["noncontrolling_interest"] == 50

    def test_cfo_keeps_sign_capex_abs(self):
        rows = [
            row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "-1000"),
            row("CF", "ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "유형자산의 취득", "-300"),
        ]
        r = _extract(rows)[2023]
        assert r["cfo"] == -1000   # 부호 유지
        assert r["tangible_asset_acquisition"] == 300  # 절대값

    def test_three_years(self):
        rows = [row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "100", "200", "300")]
        out = _extract(rows, 2023)
        assert out[2023]["cfo"] == 100
        assert out[2022]["cfo"] == 200
        assert out[2021]["cfo"] == 300


class TestNoncontrollingInterestBsOnly:
    def test_is_cis_nci_ignored(self):
        rows = [
            row("IS", "ifrs-full_ProfitLossAttributableToNoncontrollingInterests", "비지배지분에 귀속되는 당기순이익", "999"),
            row("CIS", "ifrs-full_ComprehensiveIncomeAttributableToNoncontrollingInterests", "비지배지분", "888"),
            row("BS", "ifrs-full_NoncontrollingInterests", "비지배지분", "50"),
        ]
        assert _extract(rows)[2023]["noncontrolling_interest"] == 50


class TestInterestExpensePriority:
    def test_interest_paid_beats_finance_costs(self):
        rows = [
            row("IS", "ifrs-full_FinanceCosts", "금융비용", "12000"),
            row("CF", "ifrs-full_InterestPaidClassifiedAsOperatingActivities", "이자의 지급", "800"),
        ]
        # 순서 무관하게 우선순위 높은 InterestPaid(800) 선택
        assert _extract(rows)[2023]["interest_expense"] == 800

    def test_finance_costs_fallback_when_no_interest_paid(self):
        rows = [row("IS", "ifrs-full_FinanceCosts", "금융비용", "12000")]
        assert _extract(rows)[2023]["interest_expense"] == 12000

    def test_interest_expense_abs(self):
        rows = [row("IS", "ifrs-full_InterestExpense", "이자비용", "-16761")]
        assert _extract(rows)[2023]["interest_expense"] == 16761


class TestInterestBearingDebt:
    def test_nonstandard_short_term_borrowing_by_keyword(self):
        # 삼성 케이스: 단기차입금 account_id가 비표준 → 키워드로 잡아야 함
        rows = [
            row("BS", "-표준계정코드 미사용-", "단기차입금", "7000"),
            row("BS", "ifrs-full_CurrentPortionOfLongtermBorrowings", "유동성장기부채", "1000"),
            row("BS", "ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued", "사채", "500"),
            row("BS", "ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived", "장기차입금", "3000"),
        ]
        assert _extract(rows)[2023]["interest_bearing_debt"] == 11500

    def test_two_lease_lines_summed(self):
        rows = [
            row("BS", "ifrs-full_CurrentLeaseLiabilities", "리스부채", "200"),
            row("BS", "ifrs-full_NoncurrentLeaseLiabilities", "리스부채", "500"),
        ]
        r = _extract(rows)[2023]
        assert r["interest_bearing_debt"] == 700
        # 동일 계정명 누적되어 breakdown에 합쳐짐
        assert r["_interest_bearing_debt_breakdown"]["리스부채"] == 700

    def test_cf_borrowing_rows_excluded(self):
        # CF의 '장기차입금의 차입' 같은 행은 BS 아님 → 이자부채에서 제외
        rows = [
            row("CF", "dart_ProceedsFromLongTermBorrowings", "장기차입금의 차입", "9999"),
            row("BS", "-표준계정코드 미사용-", "단기차입금", "1000"),
        ]
        assert _extract(rows)[2023]["interest_bearing_debt"] == 1000

    def test_non_debt_bs_rows_excluded(self):
        rows = [
            row("BS", "ifrs-full_TradeAndOtherCurrentPayables", "매입채무및기타채무", "5000"),
            row("BS", "dart_ShortTermWithholdings", "예수금", "300"),
            row("BS", "-표준계정코드 미사용-", "단기차입금", "1000"),
        ]
        assert _extract(rows)[2023]["interest_bearing_debt"] == 1000

    def test_subtotal_row_excluded(self):
        # '차입금및사채'(소계)는 leaf와 중복 가산되므로 키워드 폴백에서 제외.
        # 소계 + 개별 leaf가 함께 있을 때 leaf만 합산되어야 함(중복 방지).
        rows = [
            row("BS", "-표준계정코드 미사용-", "차입금및사채", "10000"),  # 소계 → 제외
            row("BS", "-표준계정코드 미사용-", "단기차입금", "7000"),
            row("BS", "ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued", "사채", "3000"),
        ]
        assert _extract(rows)[2023]["interest_bearing_debt"] == 10000  # 7000 + 3000

    def test_contra_account_subtracted(self):
        # 사채할인발행차금(차감계정, 음수)은 사채에서 '차감'되어야 함(abs로 가산 금지).
        rows = [
            row("BS", "ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued", "사채", "5000"),
            row("BS", "-표준계정코드 미사용-", "사채할인발행차금", "-200"),
        ]
        assert _extract(rows)[2023]["interest_bearing_debt"] == 4800  # 5000 - 200

    def test_standard_id_not_blocked_by_subtotal_filter(self):
        # 표준 account_id로 잡히는 행은 소계 차단('및' 등)과 무관하게 항상 포함.
        # (소계 차단은 키워드 폴백 전용 — 표준ID를 거르면 정상 차입금 누락됨)
        rows = [
            row("BS", "ifrs-full_ShorttermBorrowings", "단기차입금 및 유동성사채", "2000"),
        ]
        assert _extract(rows)[2023]["interest_bearing_debt"] == 2000


class TestCashFallbackAndParsing:
    def test_bs_cash_fallback_when_cf_missing(self):
        rows = [row("BS", "ifrs-full_CashAndCashEquivalents", "현금및현금성자산", "777")]
        assert _extract(rows)[2023]["cash_and_cash_equivalents"] == 777

    def test_cf_cash_preferred_over_bs(self):
        rows = [
            row("BS", "ifrs-full_CashAndCashEquivalents", "현금및현금성자산", "777"),
            row("CF", "dart_CashAndCashEquivalentsAtEndOfPeriodCf", "기말현금및현금성자산", "999"),
        ]
        assert _extract(rows)[2023]["cash_and_cash_equivalents"] == 999

    def test_empty_and_dash_amounts_become_zero(self):
        rows = [
            row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", ""),
            row("BS", "ifrs-full_NoncontrollingInterests", "비지배지분", "-"),
        ]
        r = _extract(rows)[2023]
        assert r["cfo"] == 0
        assert r["noncontrolling_interest"] == 0

    def test_comma_separated_amounts(self):
        rows = [row("CF", "ifrs-full_CashFlowsFromUsedInOperatingActivities", "영업활동현금흐름", "44,137,427")]
        assert _extract(rows)[2023]["cfo"] == 44137427
