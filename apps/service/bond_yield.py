"""
국채 5년 수익률 조회 (BondYield 모델)
"""
from django.apps import apps as django_apps
from django.utils import timezone
from datetime import timedelta


def get_bond_yield_5y() -> float:
    """
    캐싱된 국채 5년 수익률 조회 (BondYield 모델에서)

    BondYield 모델은 단일 레코드만 유지하며, 하루 기준으로 캐싱됩니다.
    필요 시 ECOS API를 호출하여 업데이트하는 것은 orchestrator에서 처리합니다.

    Returns:
        국채 5년 수익률 (소수 형태, 예: 0.03057 = 3.057%)
    """
    BondYieldModel = django_apps.get_model('apps', 'BondYield')

    try:
        bond_yield_obj, created = BondYieldModel.objects.get_or_create(
            id=1,
            defaults={
                'yield_value': 0.0,
                'collected_at': timezone.now() - timedelta(days=2)
            }
        )
        return bond_yield_obj.yield_value
    except Exception:
        return 0.0
