"""
순위합산 랭킹(마법공식식) 합격기준 박제 — RED 단계.

구현 전이라 apps/service/ranking.py 가 아직 없어 ModuleNotFoundError 로 실패해야 정상.
기대값은 전부 손계산 순위표에서만 가져왔다(베낄 구현 없음). 각 assert 옆에 출처를 주석으로 남김.

추론한 인터페이스(사용자 기준에서):
  from apps.service.ranking import rank_companies
  rank_companies(companies: list[dict], weights: dict | None = None) -> list[dict]
  각 회사 dict: corp_code, quality(ROIC-WACC, 클수록 좋음), price(EV/IC, 작을수록 좋음),
  growth(g, 클수록 좋음). 값은 None 가능.
  반환: 입력 dict 보존 + rank_quality/rank_price/rank_growth/score/rank 추가, rank 오름차순 정렬.
  경쟁순위: 등수 = (자기보다 더 좋은 회사 수)+1, 동점 동순위.
  None 축: 있는 값들끼리 1..k 매기고 None 은 전부 N등(전체 회사 수, 최하위).
"""
import pytest

from apps.service.ranking import rank_companies


def _by_code(result):
    return {c["corp_code"]: c for c in result}


def test_basic_4companies_rank_table():
    """
    손계산 순위표(사용자 기준 예시 4개):
      A{q:0.05, p:1.0, g:0.10}, B{q:0.03, p:2.0, g:0.20},
      C{q:0.04, p:0.5, g:0.05}, D{q:0.02, p:3.0, g:0.15}
      quality 내림차순: A1 C2 B3 D4
      price   오름차순: C1 A2 B3 D4
      growth  내림차순: B1 D2 A3 C4
      등수합(동등): A=1+2+3=6, B=3+3+1=7, C=2+1+4=7, D=4+4+2=10
      최종(경쟁순위): A 1위, B·C 동점 2위, D 4위
    """
    companies = [
        {"corp_code": "A", "quality": 0.05, "price": 1.0, "growth": 0.10},
        {"corp_code": "B", "quality": 0.03, "price": 2.0, "growth": 0.20},
        {"corp_code": "C", "quality": 0.04, "price": 0.5, "growth": 0.05},
        {"corp_code": "D", "quality": 0.02, "price": 3.0, "growth": 0.15},
    ]
    weights = {"quality": 1, "price": 1, "growth": 1}
    result = rank_companies(companies, weights)
    r = _by_code(result)

    # 축별 등수 — 손계산 순위표
    assert r["A"]["rank_quality"] == 1  # quality 내림차순 A1
    assert r["C"]["rank_quality"] == 2  # C2
    assert r["B"]["rank_quality"] == 3  # B3
    assert r["D"]["rank_quality"] == 4  # D4
    assert r["C"]["rank_price"] == 1    # price 오름차순 C1
    assert r["A"]["rank_price"] == 2    # A2
    assert r["B"]["rank_price"] == 3    # B3
    assert r["D"]["rank_price"] == 4    # D4
    assert r["B"]["rank_growth"] == 1   # growth 내림차순 B1
    assert r["D"]["rank_growth"] == 2   # D2
    assert r["A"]["rank_growth"] == 3   # A3
    assert r["C"]["rank_growth"] == 4   # C4

    # 가중 등수합(동등가중) — 손계산
    assert r["A"]["score"] == 6
    assert r["B"]["score"] == 7
    assert r["C"]["score"] == 7
    assert r["D"]["score"] == 10

    # 최종 경쟁순위 — A 1위, B·C 동점 2위, D 4위
    assert r["A"]["rank"] == 1
    assert r["B"]["rank"] == 2
    assert r["C"]["rank"] == 2
    assert r["D"]["rank"] == 4

    # 반환은 rank 오름차순 정렬 — 첫 원소가 최종 1위(A)
    assert result[0]["corp_code"] == "A"
    # 입력 dict 보존(원본 키 유지)
    assert result[0]["quality"] == 0.05


def test_tie_axis_competition_ranking_skips_rank():
    """
    동점 축 경쟁순위: 두 회사 quality 동일 → 둘 다 같은 등수, 다음 회사는 등수 건너뜀.
      X{q:0.05}, Y{q:0.05}, Z{q:0.03}
      quality 내림차순: X·Y 동점 1위(자기보다 좋은 회사 0개 → 1등), Z 는 더 좋은 회사 2개 → 3등(2등 건너뜀)
    (price/growth 는 값만 채워 두고 단언은 rank_quality 만)
    """
    companies = [
        {"corp_code": "X", "quality": 0.05, "price": 1.0, "growth": 0.10},
        {"corp_code": "Y", "quality": 0.05, "price": 2.0, "growth": 0.20},
        {"corp_code": "Z", "quality": 0.03, "price": 3.0, "growth": 0.05},
    ]
    weights = {"quality": 1, "price": 1, "growth": 1}
    r = _by_code(rank_companies(companies, weights))

    assert r["X"]["rank_quality"] == 1  # 동점 1위
    assert r["Y"]["rank_quality"] == 1  # 동점 1위
    assert r["Z"]["rank_quality"] == 3  # 2등 건너뜀(더 좋은 회사 2개 +1)


def test_none_axis_gets_worst_rank_N():
    """
    None 축 처리: price=None 회사는 price 축에서 최하위 등수 = N(전체 회사 수).
      P{p:1.0}, Q{p:2.0}, R{p:None}, N=3
      있는 값: P(1.0)1, Q(2.0)2 / R 은 None → 3등(=N)
    """
    companies = [
        {"corp_code": "P", "quality": 0.05, "price": 1.0, "growth": 0.10},
        {"corp_code": "Q", "quality": 0.03, "price": 2.0, "growth": 0.20},
        {"corp_code": "R", "quality": 0.04, "price": None, "growth": 0.05},
    ]
    weights = {"quality": 1, "price": 1, "growth": 1}
    r = _by_code(rank_companies(companies, weights))

    assert r["P"]["rank_price"] == 1  # 있는 값 중 최소
    assert r["Q"]["rank_price"] == 2
    assert r["R"]["rank_price"] == 3  # None → N=3 최하위


def test_non_equal_weights_change_final_rank():
    """
    가중치 비동등: weights={'price':2,'quality':1,'growth':1} → 가격 비중 2배.
    동일 4개 회사(test_basic 와 같은 입력)의 축등수는 그대로:
      quality: A1 C2 B3 D4 / price: C1 A2 B3 D4 / growth: B1 D2 A3 C4
    가중 등수합:
      A = q1 + p2*2 + g3 = 1+4+3 = 8
      B = q3 + p3*2 + g1 = 3+6+1 = 10
      C = q2 + p1*2 + g4 = 2+2+4 = 8
      D = q4 + p4*2 + g2 = 4+8+2 = 14
    최종 경쟁순위(score 작을수록 1위): A·C 동점 1위(8), B 3위(10), D 4위(14)
    """
    companies = [
        {"corp_code": "A", "quality": 0.05, "price": 1.0, "growth": 0.10},
        {"corp_code": "B", "quality": 0.03, "price": 2.0, "growth": 0.20},
        {"corp_code": "C", "quality": 0.04, "price": 0.5, "growth": 0.05},
        {"corp_code": "D", "quality": 0.02, "price": 3.0, "growth": 0.15},
    ]
    weights = {"price": 2, "quality": 1, "growth": 1}
    r = _by_code(rank_companies(companies, weights))

    assert r["A"]["score"] == 8
    assert r["B"]["score"] == 10
    assert r["C"]["score"] == 8
    assert r["D"]["score"] == 14

    assert r["A"]["rank"] == 1  # 동점 1위
    assert r["C"]["rank"] == 1  # 동점 1위
    assert r["B"]["rank"] == 3  # 2위 건너뜀(더 좋은 회사 2개 +1)
    assert r["D"]["rank"] == 4


def test_weights_none_uses_equal_weighting():
    """
    weights=None → settings.RANKING_WEIGHTS(동등 1:1:1) 사용.
    settings 미정의면 구현 후 정의될 것이므로, 동등가중 결과(test_basic 와 동일)를 기대.
      최종: A 1위, B·C 동점 2위, D 4위 (손계산 등수합 A6 B7 C7 D10)
    """
    companies = [
        {"corp_code": "A", "quality": 0.05, "price": 1.0, "growth": 0.10},
        {"corp_code": "B", "quality": 0.03, "price": 2.0, "growth": 0.20},
        {"corp_code": "C", "quality": 0.04, "price": 0.5, "growth": 0.05},
        {"corp_code": "D", "quality": 0.02, "price": 3.0, "growth": 0.15},
    ]
    r = _by_code(rank_companies(companies, None))

    assert r["A"]["score"] == 6
    assert r["B"]["score"] == 7
    assert r["C"]["score"] == 7
    assert r["D"]["score"] == 10
    assert r["A"]["rank"] == 1
    assert r["B"]["rank"] == 2
    assert r["C"]["rank"] == 2
    assert r["D"]["rank"] == 4
