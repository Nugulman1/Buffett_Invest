"""
1차 필터 임계값의 settings 이관(FIRST_FILTER) 합격 기준을 RED로 박제.

목적: filter.py에 하드코딩된 임계값을 settings.FIRST_FILTER로 이관 예정.
이관 후에는 override_settings로 FIRST_FILTER를 바꾸면 필터 판정이 뒤집혀야 한다.
지금은 하드코딩이라 override가 무시됨 → 아래 override 케이스들이 실패(RED).

이관 후 coder가 구현할 settings 구조(사양):
    FIRST_FILTER = {
        'OPERATING_MARGIN_MIN': 0.10,
        'OPERATING_INCOME_MAX_NEGATIVE_YEARS': 1,
        'ROE_MIN': {'large': 0.08, 'medium': 0.10, 'small': 0.12},
    }
필터 함수는 getattr(settings,'FIRST_FILTER',{기본값})로 임계를 읽어 쓸 것.

추론한 인터페이스(기존 test_filter.py 컨벤션 그대로):
- make_year(year,**kw) → YearlyFinancialDataObject
- make_company(years) → CompanyFinancialObject
- F.filter_operating_margin/filter_roe/filter_operating_income(company) → bool
규모분류 임계(apps/utils/classify.py 실제값): small < 5e11, large ≥ 1e13.
  → total_assets 1e9 = small, 2e13 = large 로 분류됨.
"""
import pytest
from django.test import override_settings

from apps.models import YearlyFinancialDataObject, CompanyFinancialObject
from apps.service.filter import CompanyFilter as F


def make_year(year, **kw):
    y = YearlyFinancialDataObject(year)
    for k, v in kw.items():
        setattr(y, k, v)
    return y


def make_company(years):
    c = CompanyFinancialObject()
    c.yearly_data = years
    return c


def first_filter(operating_margin_min=0.10,
                 operating_income_max_negative_years=1,
                 roe_min=None):
    """사양상 완전한 FIRST_FILTER dict 생성(바꿀 키만 인자로 교체).
    전체 dict를 넘겨, 구현이 키별 .get(default)든 전체 dict 기대든 무관하게 동작."""
    if roe_min is None:
        roe_min = {'large': 0.08, 'medium': 0.10, 'small': 0.12}
    return {
        'OPERATING_MARGIN_MIN': operating_margin_min,
        'OPERATING_INCOME_MAX_NEGATIVE_YEARS': operating_income_max_negative_years,
        'ROE_MIN': roe_min,
    }


# ── 1) 영업이익률: 임계 올리면 통과→탈락 ─────────────────────────
class TestOperatingMarginConfig:
    def _company_margin_012(self):
        # 평균 영업이익률 0.12 (5년 모두 0.12)
        return make_company([make_year(2020 + i, operating_margin=0.12) for i in range(5)])

    @override_settings(FIRST_FILTER=first_filter(operating_margin_min=0.15))
    def test_raising_min_above_avg_fails(self):
        # 기대값 출처: 사양 케이스1 — OPERATING_MARGIN_MIN=0.15 > avg0.12 ⟹ 탈락.
        # RED 이유: 현재 filter_operating_margin이 0.10 하드코딩이라 override 무시
        #          → avg0.12 ≥ 0.10 으로 여전히 True 반환 → 이 단언(False) 실패.
        assert F.filter_operating_margin(self._company_margin_012()) is False


# ── 2) ROE small: 임계 내리면 탈락→통과 ──────────────────────────
class TestRoeSmallConfig:
    def _small_company_roe_011(self):
        # total_assets 1e9 (<5e11) → small, ROE 평균 0.11
        return make_company([
            make_year(2020 + i, total_assets=1_000_000_000, total_equity=1000, roe=0.11)
            for i in range(5)
        ])

    @override_settings(FIRST_FILTER=first_filter(
        roe_min={'large': 0.08, 'medium': 0.10, 'small': 0.10}))
    def test_lowering_small_min_passes(self):
        # 기대값 출처: 사양 케이스2 — ROE_MIN.small=0.10 ≤ avg0.11 ⟹ 통과.
        # RED 이유: 현재 small 임계 0.12 하드코딩이라 override 무시
        #          → avg0.11 < 0.12 으로 여전히 False 반환 → 이 단언(True) 실패.
        assert F.filter_roe(self._small_company_roe_011()) is True


# ── 3) ROE large: 임계 올리면 통과→탈락 ──────────────────────────
class TestRoeLargeConfig:
    def _large_company_roe_009(self):
        # total_assets 2e13 (≥1e13) → large, ROE 평균 0.09
        return make_company([
            make_year(2020 + i, total_assets=20_000_000_000_000, total_equity=1000, roe=0.09)
            for i in range(5)
        ])

    @override_settings(FIRST_FILTER=first_filter(
        roe_min={'large': 0.10, 'medium': 0.10, 'small': 0.12}))
    def test_raising_large_min_fails(self):
        # 기대값 출처: 사양 케이스3 — ROE_MIN.large=0.10 > avg0.09 ⟹ 탈락.
        # RED 이유: 현재 large 임계 0.08 하드코딩이라 override 무시
        #          → avg0.09 ≥ 0.08 으로 여전히 True 반환 → 이 단언(False) 실패.
        assert F.filter_roe(self._large_company_roe_009()) is False


# ── 4) 영업이익 적자허용: 허용횟수 올리면 탈락→통과 ──────────────
class TestOperatingIncomeConfig:
    def _company_two_negative(self):
        # 영업이익 음수 2회 ([100,-10,100,-10,100])
        ois = [100, -10, 100, -10, 100]
        return make_company([make_year(2020 + i, operating_income=v) for i, v in enumerate(ois)])

    @override_settings(FIRST_FILTER=first_filter(operating_income_max_negative_years=2))
    def test_raising_allowed_negatives_passes(self):
        # 기대값 출처: 사양 케이스4 — MAX_NEGATIVE_YEARS=2 ≥ 적자2회 ⟹ 통과.
        # RED 이유: 현재 허용 1회 하드코딩이라 override 무시
        #          → 적자2회 > 1 으로 여전히 False 반환 → 이 단언(True) 실패.
        assert F.filter_operating_income(self._company_two_negative()) is True


# ── 5) 회귀 보증: override 없는 기본값 판정(이관 후에도 불변) ─────
# 이관 전 현재도 통과하므로 RED 아님 — 초기값 보존을 박제(GREEN 유지가 목표).
class TestDefaultBaselineRegression:
    def test_default_margin_012_passes(self):
        # 기대값 출처: 사양 — 기본 OPERATING_MARGIN_MIN=0.10 ≤ avg0.12 ⟹ 통과.
        c = make_company([make_year(2020 + i, operating_margin=0.12) for i in range(5)])
        assert F.filter_operating_margin(c) is True

    def test_default_small_roe_011_fails(self):
        # 기대값 출처: 사양 — 기본 ROE_MIN.small=0.12 > avg0.11 ⟹ 탈락.
        c = make_company([
            make_year(2020 + i, total_assets=1_000_000_000, total_equity=1000, roe=0.11)
            for i in range(5)
        ])
        assert F.filter_roe(c) is False


# ── 6) 부분 override 견고성(L1 하드닝) ───────────────────────────
# 이 config의 존재 목적이 '실험용 부분 조정'이라, 일부 키만 준 부분 dict로
# override해도 누락 키는 기본값으로 폴백해야 한다(전체 dict 부재만 폴백하던
# getattr는 부분 누락을 못 막아 KeyError). RED: 현재 _first_filter가 키를 직접
# 인덱싱해 부분 dict면 KeyError. 하드닝(기본값 병합) 후 GREEN.
class TestPartialOverrideFallback:
    @override_settings(FIRST_FILTER={'OPERATING_MARGIN_MIN': 0.15})
    def test_missing_roe_min_uses_default(self):
        # ROE_MIN 키 자체가 없음 → 기본 small 0.12 적용. small avg0.11 < 0.12 ⟹ 탈락.
        # RED: 현재 _first_filter()['ROE_MIN'] → KeyError.
        c = make_company([
            make_year(2020 + i, total_assets=1_000_000_000, total_equity=1000, roe=0.11)
            for i in range(5)
        ])
        assert F.filter_roe(c) is False

    @override_settings(FIRST_FILTER={'ROE_MIN': {'small': 0.10}})
    def test_partial_roe_min_subdict_missing_large_uses_default(self):
        # ROE_MIN에 large 키 없음 → 기본 large 0.08 폴백. large avg0.09 ≥ 0.08 ⟹ 통과.
        # RED: 현재 _first_filter()['ROE_MIN']['large'] → KeyError.
        c = make_company([
            make_year(2020 + i, total_assets=20_000_000_000_000, total_equity=1000, roe=0.09)
            for i in range(5)
        ])
        assert F.filter_roe(c) is True

    @override_settings(FIRST_FILTER={'ROE_MIN': {'small': 0.10}})
    def test_given_subdict_key_applies(self):
        # 준 small=0.10은 반영. small avg0.11 ≥ 0.10 ⟹ 통과.
        c = make_company([
            make_year(2020 + i, total_assets=1_000_000_000, total_equity=1000, roe=0.11)
            for i in range(5)
        ])
        assert F.filter_roe(c) is True
