"""
회귀 테스트: rank_passed_companies의 price축이 invested_capital<0(투하자본 음수)을
배제하는지. 음수 ic는 ev/ic 부호를 뒤집어 거짓 바겐을 가격축 최상위로 올리므로,
price=None(해당 축 최하위)로 처리되어야 한다.
"""
import pytest

from apps.models import Company, YearlyFinancialData
from apps.service.db import rank_passed_companies


@pytest.mark.django_db
def test_negative_invested_capital_is_worst_on_price_axis():
    # 정상회사 N: ev=1000, ic=100 → price=10 (유효)
    normal = Company.objects.create(
        corp_code="00000N00", company_name="정상회사",
        passed_all_filters=True, passed_second_filter=None,
    )
    YearlyFinancialData.objects.create(
        company=normal, year=2024,
        roic=0.10, wacc=0.05, ev=1000, invested_capital=100,
        sustainable_growth=0.05,
    )
    # 음수 ic회사 X: ev=70, ic=-30 → price=ev/ic=-2.33 (부호반전 거짓 바겐)
    neg = Company.objects.create(
        corp_code="00000X00", company_name="음수IC회사",
        passed_all_filters=True, passed_second_filter=None,
    )
    YearlyFinancialData.objects.create(
        company=neg, year=2024,
        roic=0.10, wacc=0.05, ev=70, invested_capital=-30,
        sustainable_growth=0.05,
    )

    result = rank_passed_companies()

    # 음수 ic는 price=None으로 배제되어 가격축 최하위(N=2) 등수.
    # 가드가 없으면 price=-2.33이 정상회사(10)보다 '싼' 1등이 되어 이 단언이 깨진다.
    assert result["00000X00"]["rank_price"] == 2
    assert result["00000N00"]["rank_price"] == 1
