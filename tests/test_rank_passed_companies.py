"""
통과기업 cross-sectional 랭킹 어댑터 rank_passed_companies() 합격조건 박제 — RED 단계.

구현 전이라 apps/service/db.py 에 rank_passed_companies 가 아직 없어 ImportError 로
실패해야 정상(db.py 모듈 자체는 존재 — recompute_and_save_ev_ic 등이 이미 있음).

추론한 인터페이스(사용자 기준에서):
  from apps.service.db import rank_passed_companies
  rank_passed_companies() -> dict[corp_code] -> {'rank':int, 'score':float,
      'rank_quality':int, 'rank_price':int, 'rank_growth':int}
  동작: Company.objects.filter(passed_all_filters=True).exclude(passed_second_filter=False)
        → 각 회사의 roic IS NOT NULL 가장 최근 연도를 대표 스냅샷으로 축값 3개 추출
        (quality=roic-wacc 클수록↑, price=ev/invested_capital 작을수록↑,
         growth=sustainable_growth 클수록↑) → 검증된 ranking.rank_companies 에 위임
        → corp_code 키 맵으로 변환 반환.

기대값 출처: 전부 rank_companies 동작 명세(클수록/작을수록 좋음, None=최하위 N등, 가중
등수합, score 경쟁순위)로 손계산. settings.RANKING_WEIGHTS=1:1:1(config 확인). 손계산표:

  N=4(통과기업 A·B·C·D만; passed_second_filter=False 인 E 는 제외)
  축값:  A{q:0.12, p:2.0, g:0.15}  C{q:0.10, p:2.0, g:0.10}
         B{q:0.02, p:6.0, g:0.05}  D{q:None, p:None, g:None}
  quality 내림차순: A1 C2 B3 D(None)4
  price   오름차순: A1·C1(둘다2.0 동점) B3 D(None)4
  growth  내림차순: A1 C2 B3 D(None)4
  등수합(1:1:1): A=1+1+1=3, C=2+1+2=5, B=3+3+3=9, D=4+4+4=12
  최종(score 작을수록 1위, 전부 distinct): A1 C2 B3 D4

핵심: 회사 C 는 2024 roic=None, 2022 roic 있음 → 대표는 2022 여야 한다. 2024 를 잘못
잡으면 C 의 quality/price/growth 가 None 이 되어 C 도 최하위(rank_quality=4)로 떨어져
아래 단언들이 깨진다(연도 선택 검증).
"""
import pytest

from apps.models import Company, YearlyFinancialData
from apps.service.db import rank_passed_companies


def _make_company(corp_code, passed_second_filter, passed_all_filters=True):
    return Company.objects.create(
        corp_code=corp_code,
        company_name=f"회사{corp_code}",
        passed_all_filters=passed_all_filters,
        passed_second_filter=passed_second_filter,
    )


@pytest.fixture
def passed_companies(db):
    # 회사 A: roic=0.20 wacc=0.08 ev=100 ic=50 g=0.15 → q=0.12 p=2.0 g=0.15
    a = _make_company("000000A0", passed_second_filter=True)
    YearlyFinancialData.objects.create(
        company=a, year=2024,
        roic=0.20, wacc=0.08, ev=100, invested_capital=50,
        sustainable_growth=0.15,
    )
    # 회사 B: roic=0.10 wacc=0.08 ev=300 ic=50 g=0.05 → q=0.02 p=6.0 g=0.05
    b = _make_company("000000B0", passed_second_filter=None)  # None 도 목록 포함
    YearlyFinancialData.objects.create(
        company=b, year=2024,
        roic=0.10, wacc=0.08, ev=300, invested_capital=50,
        sustainable_growth=0.05,
    )
    # 회사 C: 2024 roic=None(대표 아님), 2022 roic=0.15 wacc=0.05 ev=80 ic=40 g=0.10
    #         → 대표=2022, q=0.10 p=2.0 g=0.10  (★ roic 있는 최근연도 선택 검증)
    c = _make_company("000000C0", passed_second_filter=True)
    YearlyFinancialData.objects.create(
        company=c, year=2024,
        roic=None, wacc=0.05, ev=999, invested_capital=1,  # 잘못 잡으면 price 왜곡되도록 다른 값
        sustainable_growth=0.99,
    )
    YearlyFinancialData.objects.create(
        company=c, year=2022,
        roic=0.15, wacc=0.05, ev=80, invested_capital=40,
        sustainable_growth=0.10,
    )
    # 회사 D: roic 전 연도 None → 대표 스냅샷 없음 → q·p·g 모두 None → 모든 축 최하위
    d = _make_company("000000D0", passed_second_filter=None)
    YearlyFinancialData.objects.create(
        company=d, year=2024,
        roic=None, wacc=0.08, ev=500, invested_capital=50,
        sustainable_growth=0.07,
    )
    # 회사 E: passed_second_filter=False → exclude 대상(목록·맵에서 빠져야 함)
    e = _make_company("000000E0", passed_second_filter=False)
    YearlyFinancialData.objects.create(
        company=e, year=2024,
        roic=0.30, wacc=0.05, ev=10, invested_capital=100,
        sustainable_growth=0.50,
    )
    return {"A": a, "B": b, "C": c, "D": d, "E": e}


@pytest.mark.django_db
def test_returns_map_for_passed_companies_only(passed_companies):
    r = rank_passed_companies()

    # 통과기업 A·B·C·D 모두 존재, E(2차필터 False)는 제외 → 맵 크기 4(=N)
    assert set(r.keys()) == {"000000A0", "000000B0", "000000C0", "000000D0"}
    assert "000000E0" not in r  # passed_second_filter=False exclude
    assert len(r) == 4


@pytest.mark.django_db
def test_final_rank_table(passed_companies):
    r = rank_passed_companies()

    # 최종 경쟁순위 — 손계산 등수합 A3 C5 B9 D12 (전부 distinct)
    assert r["000000A0"]["rank"] == 1  # 3축 모두 최상
    assert r["000000C0"]["rank"] == 2
    assert r["000000B0"]["rank"] == 3
    assert r["000000D0"]["rank"] == 4  # 대표 스냅샷 없음 → 전 축 최하위 → 최종 최하위

    # 가중 등수합(1:1:1) — 손계산
    assert r["000000A0"]["score"] == 3
    assert r["000000C0"]["score"] == 5
    assert r["000000B0"]["score"] == 9
    assert r["000000D0"]["score"] == 12


@pytest.mark.django_db
def test_axis_ranks_and_none_worst(passed_companies):
    r = rank_passed_companies()

    # quality 내림차순: A1 C2 B3 D(None)4
    assert r["000000A0"]["rank_quality"] == 1
    assert r["000000C0"]["rank_quality"] == 2
    assert r["000000B0"]["rank_quality"] == 3
    assert r["000000D0"]["rank_quality"] == 4  # None → N=4 최하위

    # price 오름차순: A1·C1 동점(둘 다 2.0) B3 D(None)4
    assert r["000000A0"]["rank_price"] == 1
    assert r["000000C0"]["rank_price"] == 1
    assert r["000000B0"]["rank_price"] == 3
    assert r["000000D0"]["rank_price"] == 4  # None → 최하위

    # growth 내림차순: A1 C2 B3 D(None)4
    assert r["000000A0"]["rank_growth"] == 1
    assert r["000000C0"]["rank_growth"] == 2
    assert r["000000B0"]["rank_growth"] == 3
    assert r["000000D0"]["rank_growth"] == 4


@pytest.mark.django_db
def test_company_C_representative_is_roic_present_year(passed_companies):
    """
    연도 선택 검증(핵심): C 의 대표는 roic 있는 2022(q=0.10)여야 한다.
    잘못 2024(roic=None)를 잡으면 C 의 quality/price/growth 가 None → 모든 축 최하위(4)로
    떨어져 아래 단언이 깨진다.
    """
    r = rank_passed_companies()

    # C 가 D(None=최하위)보다 모든 축에서 앞서야 함 → 2022 대표 채택의 간접 증거
    assert r["000000C0"]["rank_quality"] < r["000000D0"]["rank_quality"]
    assert r["000000C0"]["rank_growth"] < r["000000D0"]["rank_growth"]
    # 2022(q=0.10) 채택 시 quality 등수 2 (A 다음). 2024(None)였다면 4(=D 동률).
    assert r["000000C0"]["rank_quality"] == 2
    # D 는 전 축 None → rank_quality == N == 4
    assert r["000000D0"]["rank_quality"] == 4
