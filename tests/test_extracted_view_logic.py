"""
view 인라인 로직 → service 함수 추출을 위한 특성화(characterization) 테스트.

목적: 추출 전 기존 인라인 동작을 그대로 고정한다. 두 함수 모두 아직 없으므로
구현 전에는 import/호출에서 RED(실패)여야 정상이다.

기대값 출처(구현 출력 복붙 아님, 명세 시맨틱에서 독립 도출):
- count_consecutive_dividend_years: "year 내림차순 정렬 후 최신부터 순회,
  dividend_paid가 None 또는 <=0이면 즉시 중단, >0이면 +1" (아젠다 명세)
- serialize_krx_daily_row: 아젠다에 명시된 12필드 KRX키→프론트키 매핑 + dict.get 시맨틱
"""
import pytest

from apps.models import YearlyFinancialDataObject
# 추론 인터페이스: IndicatorCalculator.count_consecutive_dividend_years(yearly_data:list) -> int (정적 호출)
from apps.service.calculator import IndicatorCalculator as C
# 추론 인터페이스: krx_client.serialize_krx_daily_row(row: dict) -> dict (모듈 함수)
from apps.service import krx_client


def make_year(year, dividend_paid):
    # 정규 생성자(year만) + 속성 세팅 — dict 수제작 금지 규약 준수
    y = YearlyFinancialDataObject(year)
    y.dividend_paid = dividend_paid
    return y


# ── 함수 1: 연속배당연수 ─────────────────────────────────
class TestCountConsecutiveDividendYears:
    def test_empty_list_returns_zero(self):
        # 순회할 대상 없음 → 0 (명세: 카운트 시작값 0)
        assert C.count_consecutive_dividend_years([]) == 0

    def test_latest_year_none_stops_immediately(self):
        # 최신(2022)이 None → 즉시 중단 → 0. 과거에 양수가 있어도 무관.
        data = [make_year(2020, 100), make_year(2021, 200), make_year(2022, None)]
        assert C.count_consecutive_dividend_years(data) == 0

    def test_stops_at_zero_dividend(self):
        # 2022(50)✓ 2021(30)✓ 2020(0)중단 → 2 (div<=0 경계: 0은 중단, 카운트 안 함)
        data = [make_year(2020, 0), make_year(2021, 30), make_year(2022, 50)]
        assert C.count_consecutive_dividend_years(data) == 2

    def test_all_positive_counts_all(self):
        # 2022,2021,2020 모두 양수 → 3
        data = [make_year(2022, 50), make_year(2021, 40), make_year(2020, 10)]
        assert C.count_consecutive_dividend_years(data) == 3

    def test_unsorted_input_sorted_internally(self):
        # 정렬 안 된 입력 → 내부 내림차순 정렬 후 2022(50)✓ 2021(30)✓ 2020(0)중단 → 2
        data = [make_year(2021, 30), make_year(2022, 50), make_year(2020, 0)]
        assert C.count_consecutive_dividend_years(data) == 2


# ── 함수 2: KRX 일별행 직렬화 ───────────────────────────
FULL_ROW = {
    "BAS_DD": "20260701",
    "MKT_NM": "KOSPI",
    "ISU_NM": "삼성전자",
    "TDD_CLSPRC": "70000",
    "CMPPREVDD_PRC": "500",
    "FLUC_RT": "0.72",
    "TDD_OPNPRC": "69500",
    "TDD_HGPRC": "70500",
    "TDD_LWPRC": "69000",
    "ACC_TRDVOL": "10000000",
    "ACC_TRDVAL": "700000000000",
    "MKTCAP": "418000000000000",
    # 매핑에 안 쓰이는 여분 키 — 출력에 새면 안 됨
    "ISU_CD": "005930",
}


class TestSerializeKrxDailyRow:
    def test_full_row_maps_12_fields(self):
        # 명세의 12필드 매핑 정확 검증 (KRX 원본키 → 프론트 계약키)
        out = krx_client.serialize_krx_daily_row(FULL_ROW)
        assert out == {
            "BAS_DD": "20260701",
            "IDX_CLSS": "KOSPI",          # <- MKT_NM
            "IDX_NM": "삼성전자",           # <- ISU_NM
            "CLSPRC_IDX": "70000",        # <- TDD_CLSPRC
            "CMPPREVDD_IDX": "500",       # <- CMPPREVDD_PRC
            "FLUC_RT": "0.72",
            "OPNPRC_IDX": "69500",        # <- TDD_OPNPRC
            "HGPRC_IDX": "70500",         # <- TDD_HGPRC
            "LWPRC_IDX": "69000",         # <- TDD_LWPRC
            "ACC_TRDVOL": "10000000",
            "ACC_TRDVAL": "700000000000",
            "MKTCAP": "418000000000000",
        }

    def test_missing_keys_yield_none(self):
        # 일부 키 누락 → 해당 출력값 None (.get 시맨틱). 존재 키는 정상 매핑.
        out = krx_client.serialize_krx_daily_row({"BAS_DD": "20260701", "MKT_NM": "KOSDAQ"})
        assert out["BAS_DD"] == "20260701"
        assert out["IDX_CLSS"] == "KOSDAQ"
        assert out["IDX_NM"] is None          # ISU_NM 누락
        assert out["CLSPRC_IDX"] is None       # TDD_CLSPRC 누락
        assert out["MKTCAP"] is None           # MKTCAP 누락
