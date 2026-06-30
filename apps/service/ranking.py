"""
순위합산 랭킹(마법공식식) 서비스.

각 축(quality·price·growth)에서 경쟁순위(등수 = 자기보다 더 좋은 회사 수 + 1, 동점 동순위)를
매기고, 가중 등수합(score)을 구한 뒤 score로 다시 경쟁순위(최종 rank)를 매긴다.

축 방향:
- quality, growth: 값이 클수록 좋음(내림차순)
- price: 값이 작을수록 좋음(오름차순)
None 값은 그 축에서 최하위 등수 N(=전체 회사 수)을 받는다.
"""
from django.conf import settings

_AXES = ('quality', 'price', 'growth')
# 큰 값이 좋은 축(True) / 작은 값이 좋은 축(False)
_HIGHER_IS_BETTER = {'quality': True, 'price': False, 'growth': True}

_DEFAULT_WEIGHTS = {'quality': 1.0, 'price': 1.0, 'growth': 1.0}


def _competition_ranks(values, higher_is_better):
    """
    경쟁순위 리스트 반환. values와 같은 길이.
    등수 = (자기보다 '더 좋은' 회사 수) + 1, 동점은 동순위.
    None 값은 최하위 등수 N(=전체 개수)을 받는다.
    """
    n = len(values)
    ranks = []
    for v in values:
        if v is None:
            ranks.append(n)
            continue
        if higher_is_better:
            better = sum(1 for o in values if o is not None and o > v)
        else:
            better = sum(1 for o in values if o is not None and o < v)
        ranks.append(better + 1)
    return ranks


def _resolve_weights(weights):
    """weights=None이면 settings.RANKING_WEIGHTS, dict면 부분 키 허용(누락 축 1.0)."""
    if weights is None:
        weights = getattr(settings, 'RANKING_WEIGHTS', _DEFAULT_WEIGHTS)
    return {axis: weights.get(axis, 1.0) for axis in _AXES}


def rank_companies(companies, weights=None):
    """
    회사 리스트를 순위합산 방식으로 랭킹.

    Args:
        companies: list[dict]. 각 dict는 'corp_code'와 축값 'quality'(클수록 좋음),
                   'price'(작을수록 좋음), 'growth'(클수록 좋음). 값 None 가능.
        weights: None이면 settings.RANKING_WEIGHTS 사용. dict면 부분 키 허용(누락 축 1.0).

    Returns:
        입력 dict를 복사하고 'rank_quality','rank_price','rank_growth','score','rank'를
        추가한 list. rank 오름차순 정렬. 입력 원본 dict는 변형하지 않음.
    """
    w = _resolve_weights(weights)
    # 입력 원본을 변형하지 않도록 얕은 복사
    result = [dict(c) for c in companies]

    # 축별 경쟁순위 계산
    axis_ranks = {}
    for axis in _AXES:
        values = [c.get(axis) for c in companies]
        axis_ranks[axis] = _competition_ranks(values, _HIGHER_IS_BETTER[axis])

    # 가중 등수합(score)
    for i, c in enumerate(result):
        rq = axis_ranks['quality'][i]
        rp = axis_ranks['price'][i]
        rg = axis_ranks['growth'][i]
        c['rank_quality'] = rq
        c['rank_price'] = rp
        c['rank_growth'] = rg
        c['score'] = w['quality'] * rq + w['price'] * rp + w['growth'] * rg

    # score 기준 최종 경쟁순위(작을수록 좋음, 동점 동순위)
    scores = [c['score'] for c in result]
    final_ranks = _competition_ranks(scores, higher_is_better=False)
    for c, r in zip(result, final_ranks):
        c['rank'] = r

    # rank 오름차순 정렬
    result.sort(key=lambda c: c['rank'])
    return result
