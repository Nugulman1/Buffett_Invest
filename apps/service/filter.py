"""
장기 투자 필터링 서비스
"""
from django.conf import settings

from apps.models import CompanyFinancialObject
from apps.service.calculator import IndicatorCalculator

# 최근 5년 중 영업이익 ≤ 0 인 연도 ≤ 1회
# 최근 5년 중 당기순이익 합계 > 0
# 매출액 CAGR ≥ 10%
# 영업이익률 평균 ≥ 10%
# ROE 평균 (규모별): 대기업 ≥ 8%, 중견기업 ≥ 10%, 중소기업 ≥ 12%


_FIRST_FILTER_DEFAULTS = {
    'OPERATING_MARGIN_MIN': 0.10,
    'OPERATING_INCOME_MAX_NEGATIVE_YEARS': 1,
    'ROE_MIN': {'large': 0.08, 'medium': 0.10, 'small': 0.12},
}


def _first_filter():
    """1차 필터 임계값을 settings.FIRST_FILTER에서 읽는다.
    누락 키는 기본값으로 병합 폴백 — 실험용 '부분 override'(일부 키만 지정)도
    KeyError 없이 안전하게 동작한다(전체 dict 부재만이 아니라 부분 누락까지 커버)."""
    cfg = getattr(settings, 'FIRST_FILTER', {}) or {}
    merged = dict(_FIRST_FILTER_DEFAULTS)
    merged.update(cfg)
    # ROE_MIN 하위 dict도 부분 누락(예: small만 지정) 대비 규모별 기본값 병합
    roe = dict(_FIRST_FILTER_DEFAULTS['ROE_MIN'])
    roe.update(cfg.get('ROE_MIN', {}) or {})
    merged['ROE_MIN'] = roe
    return merged


class CompanyFilter:
    """장기 투자 필터링 서비스"""
    
    @staticmethod
    def filter_operating_income(company_data: CompanyFinancialObject) -> bool:
        """
        영업이익 필터: 최근 5년 중 영업이익 ≤ 0 인 연도 ≤ 1회
        (5년 데이터가 없어도 수집된 데이터로 계산)
        
        Args:
            company_data: CompanyFinancialObject 객체
        
        Returns:
            필터 통과 여부 (bool)
        """
        if not company_data.yearly_data:
            return False
        
        # 데이터 정렬 (오름차순)
        sorted_data = sorted(company_data.yearly_data, key=lambda x: x.year)
        
        # 최근 5년 또는 모든 데이터 사용 (5년 미만인 경우)
        data_to_check = sorted_data[-5:] if len(sorted_data) >= 5 else sorted_data
        
        # 데이터 없음(None)인 연도는 제외
        valid_data = [d for d in data_to_check if d.operating_income is not None]
        if not valid_data:
            return False
        negative_count = sum(1 for d in valid_data if d.operating_income <= 0)
        return negative_count <= _first_filter()['OPERATING_INCOME_MAX_NEGATIVE_YEARS']
    
    @staticmethod
    def filter_net_income(company_data: CompanyFinancialObject) -> bool:
        """
        당기순이익 필터: 최근 5년 당기순이익 합계 > 0
        (5년 데이터가 없어도 수집된 데이터로 계산)
        
        Args:
            company_data: CompanyFinancialObject 객체
        
        Returns:
            필터 통과 여부 (bool)
        """
        if not company_data.yearly_data:
            return False
        
        # 데이터 정렬 (오름차순)
        sorted_data = sorted(company_data.yearly_data, key=lambda x: x.year)
        
        # 최근 5년 또는 모든 데이터 사용 (5년 미만인 경우)
        data_to_check = sorted_data[-5:] if len(sorted_data) >= 5 else sorted_data
        
        # 데이터 없음(None)인 연도는 제외
        valid_data = [d for d in data_to_check if d.net_income is not None]
        if not valid_data:
            return False
        total_net_income = sum(d.net_income for d in valid_data)
        return total_net_income > 0
    
    @staticmethod
    def filter_operating_margin(company_data: CompanyFinancialObject) -> bool:
        """
        영업이익률 필터: 영업이익률 평균 ≥ 10%
        (5년 데이터가 없어도 수집된 데이터로 계산)
        
        Args:
            company_data: CompanyFinancialObject 객체
        
        Returns:
            필터 통과 여부 (bool)
        """
        if not company_data.yearly_data:
            return False
        
        # 데이터 정렬 (오름차순)
        sorted_data = sorted(company_data.yearly_data, key=lambda x: x.year)
        
        # 최근 5년 또는 모든 데이터 사용 (5년 미만인 경우)
        data_to_check = sorted_data[-5:] if len(sorted_data) >= 5 else sorted_data
        
        # 데이터 없음(None)인 연도는 제외
        ratios = [d.operating_margin for d in data_to_check if d.operating_margin is not None]
        if not ratios:
            return False
        average_ratio = sum(ratios) / len(ratios)
        return average_ratio >= _first_filter()['OPERATING_MARGIN_MIN']
    
    @staticmethod
    def filter_roe(company_data: CompanyFinancialObject) -> bool:
        """
        ROE 필터: 기업 규모별 ROE 평균 임계값 적용
        - 대기업 (총자산 ≥ 10조): 평균 ROE ≥ 8%
        - 중견기업 (5천억 ≤ 총자산 < 10조): 평균 ROE ≥ 10%
        - 중소기업 (총자산 < 5천억): 평균 ROE ≥ 12%
        
        (5년 데이터가 없어도 수집된 데이터로 계산)
        
        주의:
        - 총자산은 최신 연도(year가 가장 큰 값) 데이터 사용
        - 자본총계가 0 이하인 연도는 ROE 계산에서 제외
        - 모든 연도가 자본잠식이면 필터 실패 처리
        
        Args:
            company_data: CompanyFinancialObject 객체
        
        Returns:
            필터 통과 여부 (bool)
        """
        if not company_data.yearly_data:
            return False
        
        # 최신 연도 총자산으로 기업 규모 분류 (total_assets가 None이 아닌 연도 사용)
        from apps.utils import classify_company_size
        sorted_data = sorted(company_data.yearly_data, key=lambda x: x.year)
        valid_for_assets = [d for d in reversed(sorted_data) if d.total_assets is not None]
        if not valid_for_assets:
            return False
        latest_total_assets = valid_for_assets[0].total_assets
        company_size = classify_company_size(latest_total_assets)
        
        roe_thresholds = _first_filter()['ROE_MIN']
        threshold = roe_thresholds[company_size]
        
        data_to_check = sorted_data[-5:] if len(sorted_data) >= 5 else sorted_data
        roe_values = []
        for d in data_to_check:
            if d.total_equity is not None and d.total_equity > 0 and d.roe is not None:
                roe_values.append(d.roe)
        if not roe_values:
            return False
        average_roe = sum(roe_values) / len(roe_values)
        return average_roe >= threshold
    
    @classmethod
    def apply_all_filters(cls, company_data: CompanyFinancialObject) -> None:
        """
        모든 필터를 적용하고 결과를 CompanyFinancialObject에 저장
        
        하나라도 false면 passed_all_filters를 false로 설정합니다.
        
        Args:
            company_data: CompanyFinancialObject 객체 (in-place 수정)
        """
        # 각 필터 적용
        company_data.filter_operating_income = cls.filter_operating_income(company_data)
        company_data.filter_net_income = cls.filter_net_income(company_data)
        company_data.filter_operating_margin = cls.filter_operating_margin(company_data)
        company_data.filter_roe = cls.filter_roe(company_data)

        # 전체 필터 통과 여부: 모든 필터가 True여야 함
        company_data.passed_all_filters = (
            company_data.filter_operating_income and
            company_data.filter_net_income and
            company_data.filter_operating_margin and
            company_data.filter_roe
        )

    @staticmethod
    def check_second_filter(corp_code: str) -> bool:
        """
        2차 필터: 최근 3년 평균 ROIC - 최근 3년 평균 WACC >= settings.SECOND_FILTER_ROIC_WACC_SPREAD 이면 True.
        DB YearlyFinancialData에서 해당 기업의 최근 3년 roic, wacc 평균 사용.
        """
        spread = getattr(settings, 'SECOND_FILTER_ROIC_WACC_SPREAD', 0.02)
        from apps.service.db import load_recent_roic_wacc  # lazy: db.py가 filter를 lazy import(순환 방지)
        latest_three = load_recent_roic_wacc(corp_code, limit=3)
        valid = [d for d in latest_three if d.get('roic') is not None and d.get('wacc') is not None]
        if not valid:
            return False
        avg_roic = sum(d['roic'] for d in valid) / len(valid)
        avg_wacc = sum(d['wacc'] for d in valid) / len(valid)
        return (avg_roic - avg_wacc) >= spread

    @staticmethod
    def evaluate_second_filter(corp_code: str) -> dict:
        """
        2차 필터 통과 여부 + 무차입 의심(정보 노출)을 함께 반환.

        'passed'는 기존 check_second_filter를 그대로 위임해 동일 값을 쓴다 —
        무차입 의심이어도 통과/탈락 판정은 바꾸지 않는다(정보 노출만).
        'no_debt_suspect'/'reason'은 surface 윈도우 = check_second_filter가 보는
        **최근 3년 raw 이자부채**(order_by('-year')[:3])를
        IndicatorCalculator.flag_no_debt_suspect에 넘긴 결과다(DEC-6). 여기서
        roic/wacc not-None valid 필터는 적용하지 않는다 — 커플링상 valid 윈도우는
        부채0 행을 구조적으로 배제해 무차입 의심을 영원히 못 잡기 때문이다
        (orchestrator.py:184-186이 '이자부채 0/None ⟹ roic/wacc=None'을 강제하고
        이것이 roic/wacc의 유일한 산출 경로라, valid 행집합은 곧 부채>0 행들뿐이다.
        진짜 무차입 회사는 roic/wacc 전부 None → valid=[] → 의심을 침묵시킨다).
        윈도우는 '최근 3년'이다(전 연도 아님): check_second_filter의 [:3] 결정
        윈도우와 동일 범위 — 전 연도 전체를 넘기면 옛 차입연도가 최근 무차입을
        가린다. 순수함수 flag_no_debt_suspect 자체는 사양 유지 — 바꾸는 건 넘기는
        입력의 윈도우뿐. ORM 객체로 가져와 .interest_bearing_debt 속성에 접근한다.

        Args:
            corp_code: 기업 코드 (YearlyFinancialData.company_id)

        Returns:
            {'passed': bool, 'no_debt_suspect': bool, 'reason': str}
        """
        passed = CompanyFilter.check_second_filter(corp_code)

        from apps.service.db import load_recent_yearly_data  # lazy: db.py가 filter를 lazy import(순환 방지)
        recent_three = load_recent_yearly_data(corp_code, limit=3)
        # surface 윈도우 = 최근 3년 raw 이자부채(valid 필터 미적용, DEC-6).
        no_debt_suspect, reason = IndicatorCalculator.flag_no_debt_suspect(recent_three)

        return {
            'passed': passed,
            'no_debt_suspect': no_debt_suspect,
            'reason': reason,
        }

