"""
db.py 레이어 함수 회귀 안전망 (T10에서 뷰 ORM을 db.py로 이관 — 그 계약을 검증).

뷰는 단위테스트가 어려우므로, 뷰가 의존하는 db 함수의 입출력 계약을 django_db로 고정한다.
"""
import pytest

from apps.models import Company, YearlyFinancialData
from apps.service import db


def _make_company(corp_code="00000001", name="테스트기업", **kw):
    return Company.objects.create(corp_code=corp_code, company_name=name, **kw)


# ── 메모 upsert ──────────────────────────────────────────
@pytest.mark.django_db
class TestUpsertMemo:
    def test_create_and_update(self):
        r = db.upsert_company_memo("00000001", "첫메모")
        assert r["created"] is True
        assert r["memo"] == "첫메모"
        assert r["memo_updated_at"] is not None
        # 같은 corp_code 재호출 → update
        r2 = db.upsert_company_memo("00000001", "수정메모")
        assert r2["created"] is False
        assert r2["memo"] == "수정메모"

    def test_empty_memo_clears_timestamp(self):
        r = db.upsert_company_memo("00000001", "")
        assert r["memo_updated_at"] is None


# ── 계산기 단일 연도 조회 ──────────────────────────────────
@pytest.mark.django_db
class TestCalculatorYearData:
    def test_found(self):
        c = _make_company()
        YearlyFinancialData.objects.create(company=c, year=2024, total_equity=500, operating_income=80)
        data, err = db.get_calculator_year_data("00000001", 2024)
        assert err is None
        assert data == {"total_equity": 500, "operating_income": 80}

    def test_company_missing(self):
        data, err = db.get_calculator_year_data("99999999", 2024)
        assert data is None
        assert "찾을 수 없습니다" in err

    def test_year_missing(self):
        _make_company()
        data, err = db.get_calculator_year_data("00000001", 2099)
        assert data is None
        assert "2099년" in err


# ── 시총/사업보고서 조회 ──────────────────────────────────
@pytest.mark.django_db
class TestCompanyLookups:
    def test_market_cap(self):
        _make_company(market_cap=12345)
        assert db.get_company_market_cap("00000001") == 12345
        assert db.get_company_market_cap("99999999") is None

    def test_market_cap_info(self):
        _make_company(market_cap=999)
        info = db.get_company_market_cap_info("00000001")
        assert info["market_cap"] == 999
        assert info["market_cap_updated_at"] is None  # 미설정
        assert db.get_company_market_cap_info("99999999") is None

    def test_annual_report_info(self):
        _make_company(latest_annual_rcept_no="20240401000001", latest_annual_report_year=2023)
        info = db.get_annual_report_info("00000001")
        assert info == {"rcept_no": "20240401000001", "year": 2023}
        assert db.get_annual_report_info("99999999") is None


# ── EV/IC 재계산·저장 ─────────────────────────────────────
@pytest.mark.django_db
class TestRecomputeEvIc:
    def _seed(self):
        c = _make_company()
        YearlyFinancialData.objects.create(
            company=c, year=2024, total_equity=4000, interest_bearing_debt=2000,
            cash_and_cash_equivalents=1000, noncontrolling_interest=500, roic=0.1, wacc=0.08,
        )
        return c

    def test_with_market_cap_persists(self):
        self._seed()
        results = db.recompute_and_save_ev_ic("00000001", market_cap=10000)
        assert len(results) == 1
        r = results[0]
        assert r["invested_capital"] == 5000          # 4000+2000-1000
        assert r["ev"] == 11500                        # 10000+2000-1000+500
        assert r["ev_over_ic"] == pytest.approx(2.3)
        # DB에 영속화됐는지
        yd = YearlyFinancialData.objects.get(company_id="00000001", year=2024)
        assert yd.invested_capital == 5000
        assert yd.ev == 11500

    def test_market_cap_none_ev_none(self):
        self._seed()
        results = db.recompute_and_save_ev_ic("00000001", market_cap=None)
        assert results[0]["ev"] is None
        assert results[0]["invested_capital"] == 5000

    def test_no_data_returns_none(self):
        _make_company()  # 연간 데이터 없음
        assert db.recompute_and_save_ev_ic("00000001", market_cap=10000) is None

    def test_target_year_filter(self):
        c = self._seed()
        YearlyFinancialData.objects.create(company=c, year=2023, total_equity=1000)
        results = db.recompute_and_save_ev_ic("00000001", market_cap=10000, target_year=2024)
        assert [r["year"] for r in results] == [2024]


# ── 통과 기업 목록 / 검색 ──────────────────────────────────
@pytest.mark.django_db
class TestPassedAndSearch:
    def test_excludes_only_second_filter_false(self):
        # 1차 통과 + 2차(None/True)는 노출, 2차 False만 제외
        _make_company("00000001", "에이", passed_all_filters=True, passed_second_filter=None)
        _make_company("00000002", "비이", passed_all_filters=True, passed_second_filter=True)
        _make_company("00000003", "씨이", passed_all_filters=True, passed_second_filter=False)
        _make_company("00000004", "디이", passed_all_filters=False)  # 1차 미통과
        result = db.query_passed_companies(page=1, page_size=10)
        codes = {c["corp_code"] for c in result["companies"]}
        assert codes == {"00000001", "00000002"}
        assert result["total"] == 2

    def test_pagination(self):
        for i in range(1, 6):
            _make_company(f"0000000{i}", f"기업{i}", passed_all_filters=True)
        page1 = db.query_passed_companies(page=1, page_size=2)
        assert len(page1["companies"]) == 2
        assert page1["total"] == 5
        assert page1["total_pages"] == 3

    def test_search_by_name_and_code(self):
        _make_company("00000001", "삼성전자")
        _make_company("00000002", "현대차")
        by_name = db.search_companies_in_db("삼성", 10)
        assert [c["corp_code"] for c in by_name] == ["00000001"]
        by_code = db.search_companies_in_db("00000002", 10)
        assert [c["corp_code"] for c in by_code] == ["00000002"]
