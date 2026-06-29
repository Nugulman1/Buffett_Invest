"""
[기준 A] recompute_and_save_ev_ic 의 이자부채0 가드 일관성 RED 박제.

설계 의도: 수집 경로 _fill_advanced_indicators 는 interest_bearing_debt 가 0/None 인
연도를 '미포착 의심(셀트리온형)'으로 보고 invested_capital/ev 를 None 으로 제외한다.
그런데 recompute_and_save_ev_ic 는 `interest_bearing_debt or 0` 으로 모든 연도 IC/EV 를
계산·저장해 제외했던 값을 되살린다. 이 테스트는 '이자부채0/None 연도는 재계산 후에도
DB의 invested_capital·ev 가 None' 이어야 함을 박제한다.

구현 전 RED 사유: 현재 가드가 없어 0/None 이자부채 연도에도 IC·EV 가 숫자로 채워짐.
기대값 출처: 모두 위 설계 의도(기준 A 본문)에서 직접 도출. 코드 출력 베끼지 않음.
추론한 인터페이스: recompute_and_save_ev_ic(corp_code, market_cap) -> DB의
YearlyFinancialData.invested_capital / .ev 를 갱신. Company PK=corp_code (모델 확인).
"""
import pytest

from apps.models import Company, YearlyFinancialData
from apps.service.db import recompute_and_save_ev_ic


CORP = "00000099"
MARKET_CAP = 400_000_000_000  # market_cap 을 주므로 ev 도 값이 나와야(가드 통과 연도)


@pytest.fixture
def company_with_mixed_debt(db):
    """같은 회사에 이자부채>0 / 0 / None 연도를 각각 만든다."""
    c = Company.objects.create(corp_code=CORP, company_name="가드테스트")
    # 이자부채>0 연도 → IC/EV 계산 대상(가드 통과)
    YearlyFinancialData.objects.create(
        company=c, year=2022,
        total_equity=100_000_000_000,
        interest_bearing_debt=20_000_000_000,
        cash_and_cash_equivalents=5_000_000_000,
    )
    # 이자부채=0 연도 → 미포착 의심으로 IC/EV 제외 대상
    YearlyFinancialData.objects.create(
        company=c, year=2023,
        total_equity=100_000_000_000,
        interest_bearing_debt=0,
        cash_and_cash_equivalents=5_000_000_000,
    )
    # 이자부채=None 연도 → 0 과 동일하게 제외 대상
    YearlyFinancialData.objects.create(
        company=c, year=2024,
        total_equity=100_000_000_000,
        interest_bearing_debt=None,
        cash_and_cash_equivalents=5_000_000_000,
    )
    return c


@pytest.mark.django_db
def test_zero_debt_year_ic_ev_remain_none(company_with_mixed_debt):
    """이자부채=0 연도는 재계산 후에도 invested_capital·ev 가 None (기준 A)."""
    recompute_and_save_ev_ic(CORP, MARKET_CAP)
    yd = YearlyFinancialData.objects.get(company_id=CORP, year=2023)
    assert yd.invested_capital is None, "이자부채0 연도 IC는 None 이어야(가드)"
    assert yd.ev is None, "이자부채0 연도 EV는 None 이어야(가드)"


@pytest.mark.django_db
def test_none_debt_year_ic_ev_remain_none(company_with_mixed_debt):
    """이자부채=None 연도도 0 과 동일하게 invested_capital·ev 가 None (기준 A)."""
    recompute_and_save_ev_ic(CORP, MARKET_CAP)
    yd = YearlyFinancialData.objects.get(company_id=CORP, year=2024)
    assert yd.invested_capital is None, "이자부채None 연도 IC는 None 이어야(가드)"
    assert yd.ev is None, "이자부채None 연도 EV는 None 이어야(가드)"


@pytest.mark.django_db
def test_positive_debt_year_ic_ev_filled(company_with_mixed_debt):
    """이자부채>0 연도는 invested_capital·ev 가 값으로 채워진다(가드 통과, 기준 A)."""
    recompute_and_save_ev_ic(CORP, MARKET_CAP)
    yd = YearlyFinancialData.objects.get(company_id=CORP, year=2022)
    assert yd.invested_capital is not None, "이자부채>0 연도 IC는 값이어야"
    assert yd.ev is not None, "market_cap 줬으니 이자부채>0 연도 EV도 값이어야"
