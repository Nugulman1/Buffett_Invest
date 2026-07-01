"""
DB 레이어: 분기보고서 저장/조회, 기업·after_date 조회, 연간 Company 저장/조회

Companies 뷰는 이 모듈과 DART 서비스만 호출하고, 직접 ORM 사용하지 않음.
"""
import threading
import time

from django.apps import apps as django_apps
from django.utils import timezone
from django.db import transaction
from django.db.utils import OperationalError

from apps.models import CompanyFinancialObject, YearlyFinancialDataObject


def get_company_for_quarterly_collect(corp_code: str):
    """
    분기 수집용 기업 조회 (사업보고서 날짜 무관, 최근 3개 분기만 수집)

    Args:
        corp_code: 고유번호 (8자리)

    Returns:
        (company,) 또는 (None, error_message)
    """
    CompanyModel = django_apps.get_model("apps", "Company")
    try:
        company = CompanyModel.objects.get(corp_code=corp_code)
    except CompanyModel.DoesNotExist:
        return (None, "기업을 찾을 수 없습니다. 먼저 연도별 데이터를 수집해주세요.")
    return (company,)


def save_quarterly_financial_data(company, quarterly_data_list: list) -> int:
    """
    분기보고서 재무 데이터 DB 저장

    Args:
        company: Company 모델 인스턴스
        quarterly_data_list: [(year, quarter, quarterly_data, rcept_no, reprt_code), ...]
            quarterly_data: YearlyFinancialDataObject (분기용)

    Returns:
        저장된 건수
    """
    QuarterlyFinancialDataModel = django_apps.get_model(
        "apps", "QuarterlyFinancialData"
    )
    now = timezone.now()
    collected_count = 0

    with transaction.atomic():
        for year, quarter, quarterly_data, rcept_no, reprt_code in quarterly_data_list:
            QuarterlyFinancialDataModel.objects.update_or_create(
                company=company,
                year=year,
                quarter=quarter,
                defaults={
                    "reprt_code": reprt_code or "",
                    "rcept_no": rcept_no,
                    "revenue": quarterly_data.revenue,
                    "operating_income": quarterly_data.operating_income,
                    "net_income": quarterly_data.net_income,
                    "total_assets": quarterly_data.total_assets,
                    "total_equity": quarterly_data.total_equity,
                    "operating_margin": quarterly_data.operating_margin,
                    "roe": 0.0,
                    "collected_at": now,
                },
            )
            collected_count += 1

    return collected_count


def load_quarterly_financial_data(corp_code: str) -> list[dict]:
    """
    분기보고서 재무 데이터 조회

    Args:
        corp_code: 고유번호 (8자리)

    Returns:
        [{"year": ..., "quarter": ..., "reprt_code": ..., ...}, ...]
    """
    CompanyModel = django_apps.get_model("apps", "Company")
    QuarterlyFinancialDataModel = django_apps.get_model(
        "apps", "QuarterlyFinancialData"
    )

    try:
        company = CompanyModel.objects.get(corp_code=corp_code)
    except CompanyModel.DoesNotExist:
        return []

    qs = QuarterlyFinancialDataModel.objects.filter(company=company).order_by(
        "-year", "-quarter"
    )
    return [
        {
            "year": qd.year,
            "quarter": qd.quarter,
            "reprt_code": qd.reprt_code,
            "rcept_no": qd.rcept_no,
            "revenue": qd.revenue,
            "operating_income": qd.operating_income,
            "net_income": qd.net_income,
            "total_assets": qd.total_assets,
            "total_equity": qd.total_equity,
            "operating_margin": qd.operating_margin,
            "roe": qd.roe,
            "roic": None,
            "wacc": None,
            "collected_at": qd.collected_at.isoformat() if qd.collected_at else None,
        }
        for qd in qs
    ]


def load_company_from_db(corp_code: str) -> tuple[CompanyFinancialObject | None, object | None]:
    """
    DB에서 Company 및 YearlyFinancialData 모델을 조회하여 CompanyFinancialObject로 변환

    Args:
        corp_code: 고유번호 (8자리)

    Returns:
        (CompanyFinancialObject, Company) 또는 (None, None). Company는 memo/수집여부 판단용.
    """
    CompanyModel = django_apps.get_model('apps', 'Company')
    YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')

    try:
        company = CompanyModel.objects.prefetch_related('yearly_data').get(corp_code=corp_code)
        yearly_data_list = list(company.yearly_data.all().order_by('year'))

        company_data = CompanyFinancialObject()
        company_data.corp_code = company.corp_code
        company_data.company_name = company.company_name or ""
        company_data.passed_all_filters = company.passed_all_filters
        company_data.filter_operating_income = company.filter_operating_income
        company_data.filter_net_income = company.filter_net_income
        company_data.filter_operating_margin = company.filter_operating_margin
        company_data.filter_roe = company.filter_roe

        for yearly_data_db in yearly_data_list:
            yearly_data_obj = YearlyFinancialDataObject(year=yearly_data_db.year)
            # None(데이터 없음) 보존, DB NULL -> None
            yearly_data_obj.revenue = yearly_data_db.revenue
            yearly_data_obj.operating_income = yearly_data_db.operating_income
            yearly_data_obj.net_income = yearly_data_db.net_income
            yearly_data_obj.total_assets = yearly_data_db.total_assets
            yearly_data_obj.total_equity = yearly_data_db.total_equity
            yearly_data_obj.operating_margin = yearly_data_db.operating_margin
            yearly_data_obj.roe = yearly_data_db.roe
            yearly_data_obj.total_liabilities = getattr(yearly_data_db, 'total_liabilities', None)
            yearly_data_obj.debt_ratio = getattr(yearly_data_db, 'debt_ratio', None)
            yearly_data_obj.interest_bearing_debt = yearly_data_db.interest_bearing_debt or 0
            yearly_data_obj.interest_expense = getattr(yearly_data_db, 'interest_expense', None) or 0
            yearly_data_obj.cash_and_cash_equivalents = getattr(yearly_data_db, 'cash_and_cash_equivalents', None) or 0
            yearly_data_obj.noncontrolling_interest = getattr(yearly_data_db, 'noncontrolling_interest', None) or 0
            yearly_data_obj.dividend_paid = getattr(yearly_data_db, "dividend_paid", None)
            yearly_data_obj.dividend_payout_ratio = getattr(yearly_data_db, "dividend_payout_ratio", None)
            yearly_data_obj.selling_admin_expense_ratio = getattr(yearly_data_db, "selling_admin_expense_ratio", None)
            yearly_data_obj.fcf = yearly_data_db.fcf
            yearly_data_obj.roic = yearly_data_db.roic
            yearly_data_obj.wacc = yearly_data_db.wacc
            yearly_data_obj.ev = getattr(yearly_data_db, 'ev', None)
            yearly_data_obj.invested_capital = getattr(yearly_data_db, 'invested_capital', None)
            yearly_data_obj.sustainable_growth = getattr(yearly_data_db, 'sustainable_growth', None)
            yearly_data_obj.altman_z = getattr(yearly_data_db, 'altman_z', None)
            yearly_data_obj.altman_z_class = getattr(yearly_data_db, 'altman_z_class', None)
            yearly_data_obj.zmijewski = getattr(yearly_data_db, 'zmijewski', None)
            yearly_data_obj.zmijewski_flag = getattr(yearly_data_db, 'zmijewski_flag', None)

            company_data.yearly_data.append(yearly_data_obj)

        return (company_data, company)

    except CompanyModel.DoesNotExist:
        return (None, None)


# 병렬 수집 시 SQLite 쓰기 충돌 방지용 락
db_write_lock = threading.Lock()


def run_with_write_lock_retry(fn, *, max_retries: int = 5):
    """
    db_write_lock으로 직렬화 + SQLite 'database is locked' 시 지수백오프 재시도하며 fn() 실행.

    모든 쓰기 경로(배치 수집·뷰 저장·KRX 시총 갱신)가 이 한 헬퍼로 동시성 보호를 일원화(T9).
    fn은 보통 transaction.atomic() 블록을 감싼 무인자 콜러블. 재시도 대비 멱등이어야 함.
    """
    for attempt in range(max_retries):
        try:
            with db_write_lock:
                return fn()
        except OperationalError as e:
            if "locked" not in str(e).lower() or attempt >= max_retries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))


def save_company_to_db(company_data: CompanyFinancialObject) -> None:
    """
    CompanyFinancialObject를 Django 모델로 변환하여 DB에 저장

    트랜잭션으로 원자성 보장: Company와 YearlyFinancialData 저장이 모두 성공하거나 모두 실패.
    병렬 수집 시 한 번에 한 스레드만 쓰기하도록 락 사용.
    SQLite "database is locked" 발생 시 최대 5회까지 대기 후 재시도.

    Args:
        company_data: CompanyFinancialObject 객체
    """
    CompanyModel = django_apps.get_model('apps', 'Company')
    YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
    now = timezone.now()

    def _do():
        with transaction.atomic():
            company, created = CompanyModel.objects.update_or_create(
                corp_code=company_data.corp_code,
                defaults={
                    'company_name': company_data.company_name,
                    'last_collected_at': now,
                    'passed_all_filters': company_data.passed_all_filters,
                    'filter_operating_income': company_data.filter_operating_income,
                    'filter_net_income': company_data.filter_net_income,
                    'filter_operating_margin': company_data.filter_operating_margin,
                    'filter_roe': company_data.filter_roe,
                    'latest_annual_rcept_no': getattr(company_data, 'latest_annual_rcept_no', None),
                    'latest_annual_report_year': getattr(company_data, 'latest_annual_report_year', None),
                }
            )

            for yearly_data in company_data.yearly_data:
                YearlyFinancialDataModel.objects.update_or_create(
                    company=company,
                    year=yearly_data.year,
                    defaults={
                        'revenue': yearly_data.revenue,
                        'operating_income': yearly_data.operating_income,
                        'net_income': yearly_data.net_income,
                        'total_assets': yearly_data.total_assets,
                        'total_equity': yearly_data.total_equity,
                        'operating_margin': yearly_data.operating_margin,
                        'roe': yearly_data.roe,
                        'debt_ratio': getattr(yearly_data, 'debt_ratio', None),
                        'interest_bearing_debt': yearly_data.interest_bearing_debt or 0,
                        'interest_expense': getattr(yearly_data, 'interest_expense', None),
                        'cash_and_cash_equivalents': getattr(yearly_data, 'cash_and_cash_equivalents', None),
                        'noncontrolling_interest': getattr(yearly_data, 'noncontrolling_interest', None),
                        'current_assets': getattr(yearly_data, 'current_assets', None),
                        'noncurrent_assets': getattr(yearly_data, 'noncurrent_assets', None),
                        'current_liabilities': getattr(yearly_data, 'current_liabilities', None),
                        'noncurrent_liabilities': getattr(yearly_data, 'noncurrent_liabilities', None),
                        'total_liabilities': getattr(yearly_data, 'total_liabilities', None),
                        'retained_earnings': getattr(yearly_data, 'retained_earnings', None),
                        'dividend_paid': getattr(yearly_data, 'dividend_paid', None),
                        'ev': getattr(yearly_data, 'ev', None),
                        'invested_capital': getattr(yearly_data, 'invested_capital', None),
                        'selling_admin_expense_ratio': getattr(yearly_data, 'selling_admin_expense_ratio', None),
                        # ROIC/WACC/FCF/배당성향: 배치 자동계산(T3) 결과 영속화. 미계산 연도는 None.
                        'roic': getattr(yearly_data, 'roic', None),
                        'wacc': getattr(yearly_data, 'wacc', None),
                        'fcf': getattr(yearly_data, 'fcf', None),
                        'dividend_payout_ratio': getattr(yearly_data, 'dividend_payout_ratio', None),
                        # 내재가치 5선 신규(연도별 저장). 미계산 연도는 None.
                        'sustainable_growth': getattr(yearly_data, 'sustainable_growth', None),
                        'altman_z': getattr(yearly_data, 'altman_z', None),
                        'altman_z_class': getattr(yearly_data, 'altman_z_class', None),
                        'zmijewski': getattr(yearly_data, 'zmijewski', None),
                        'zmijewski_flag': getattr(yearly_data, 'zmijewski_flag', None),
                    }
                )
            # yearly_indicators는 함수 내 임시 데이터(ROE 등 채움용). DB에 저장하지 않음.

    run_with_write_lock_retry(_do)


def update_company_market_cap(corp_code: str, market_cap, updated_at) -> None:
    """
    Company.market_cap / market_cap_updated_at 단일 갱신 게이트웨이.

    krx_client.fetch_and_save_company_market_cap·orchestrator._fill_market_cap_and_ev가
    직접 ORM 대신 이 함수를 호출(T-DB위임). 쓰기 락+재시도로 보호.
    """
    CompanyModel = django_apps.get_model("apps", "Company")

    def _do():
        with transaction.atomic():
            CompanyModel.objects.filter(corp_code=corp_code).update(
                market_cap=market_cap,
                market_cap_updated_at=updated_at,
            )

    run_with_write_lock_retry(_do)


def iter_companies_for_market_cap_update():
    """
    시총 일괄 갱신용: 전 회사의 corp_code/market_cap만 스트리밍(iterator) 조회.

    krx_client.update_all_company_market_caps가 직접 ORM 대신 호출(T-DB위임).
    읽기 전용, 락 없음.
    """
    CompanyModel = django_apps.get_model("apps", "Company")
    return CompanyModel.objects.only("corp_code", "market_cap").iterator()


def bulk_update_market_caps(companies: list, batch_size: int = 500) -> None:
    """
    Company 인스턴스 리스트(각 market_cap/market_cap_updated_at 세팅 완료)를 일괄 갱신.

    krx_client.update_all_company_market_caps가 직접 bulk_update 대신 호출(T-DB위임).
    쓰기 락+재시도로 보호.
    """
    CompanyModel = django_apps.get_model("apps", "Company")

    def _do():
        CompanyModel.objects.bulk_update(
            companies, ["market_cap", "market_cap_updated_at"], batch_size=batch_size
        )

    run_with_write_lock_retry(_do)


def get_or_create_bond_yield(defaults: dict):
    """
    BondYield 단일 레코드(id=1) 조회/기본생성 게이트웨이. (bond_yield_obj, created) 반환.

    bond_yield.py의 조회는 원래 쓰기 락이 없었다(조회 성격) — 동작 보존을 위해
    여기서도 run_with_write_lock_retry를 씌우지 않는다.
    """
    BondYieldModel = django_apps.get_model('apps', 'BondYield')
    return BondYieldModel.objects.get_or_create(id=1, defaults=defaults)


def load_recent_roic_wacc(corp_code: str, limit: int = 3) -> list[dict]:
    """
    해당 기업의 최근 N년(연도 내림차순) roic/wacc 조회. [{"roic": ..., "wacc": ...}, ...].

    filter.check_second_filter의 최근3년 조회를 게이트웨이로 위임(T-DB위임). 읽기 전용,
    락 없음. 순환 방지: filter.py에서 이 함수는 lazy import(db.py가 filter를 이미
    lazy import하므로 상호 순환 방지).
    """
    YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
    return list(
        YearlyFinancialDataModel.objects.filter(company_id=corp_code)
        .order_by('-year')
        .values('roic', 'wacc')[:limit]
    )


def load_recent_yearly_data(corp_code: str, limit: int = 3) -> list:
    """
    해당 기업의 최근 N년(연도 내림차순) YearlyFinancialData ORM 객체 리스트 조회.

    filter.evaluate_second_filter의 flag_no_debt_suspect 입력(전체 ORM 객체,
    .interest_bearing_debt 등 속성 접근 필요)을 게이트웨이로 위임(T-DB위임).
    읽기 전용, 락 없음. 순환 방지: filter.py에서 이 함수는 lazy import(db.py가
    filter를 이미 lazy import하므로 상호 순환 방지).
    """
    YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
    return list(
        YearlyFinancialDataModel.objects.filter(company_id=corp_code)
        .order_by('-year')[:limit]
    )


def update_second_filter_result(corp_code: str) -> None:
    """
    DB의 최근 3년 ROIC/WACC로 2차 필터 재계산 → Company.passed_second_filter 반영.

    배치 자동수집(T3)에서 ROIC/WACC 저장 후 호출. 쓰기 락+재시도로 보호.
    """
    from apps.service.filter import CompanyFilter
    CompanyModel = django_apps.get_model('apps', 'Company')
    passed = CompanyFilter.check_second_filter(corp_code)

    def _do():
        with transaction.atomic():
            CompanyModel.objects.filter(corp_code=corp_code).update(
                passed_second_filter=passed
            )

    run_with_write_lock_retry(_do)


# ──────────────────────────────────────────────────────────────────
# 뷰 레이어 계약(T10): companies 뷰는 .objects를 직접 쓰지 않고 아래 함수만 호출.
# 쓰기는 run_with_write_lock_retry로 동시성 보호(T9).
# ──────────────────────────────────────────────────────────────────

def upsert_company_memo(corp_code: str, memo: str) -> dict:
    """기업 메모 upsert. {"corp_code", "memo", "memo_updated_at"(iso|None), "created"} 반환."""
    CompanyModel = django_apps.get_model('apps', 'Company')
    now = timezone.now()

    def _do():
        return CompanyModel.objects.update_or_create(
            corp_code=corp_code,
            defaults={"memo": memo, "memo_updated_at": now if memo else None},
        )

    company, created = run_with_write_lock_retry(_do)
    return {
        "corp_code": company.corp_code,
        "memo": company.memo,
        "memo_updated_at": company.memo_updated_at.isoformat() if company.memo_updated_at else None,
        "created": created,
    }


def get_calculator_year_data(corp_code: str, year: int) -> tuple[dict | None, str | None]:
    """계산기용 단일 연도 데이터 조회. (data, error). data는 total_equity/operating_income."""
    CompanyModel = django_apps.get_model('apps', 'Company')
    YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
    try:
        company = CompanyModel.objects.get(corp_code=corp_code)
    except CompanyModel.DoesNotExist:
        return None, f"기업코드 {corp_code}에 해당하는 데이터를 찾을 수 없습니다."
    try:
        yd = YearlyFinancialDataModel.objects.get(company=company, year=year)
    except YearlyFinancialDataModel.DoesNotExist:
        return None, f"{year}년 데이터를 찾을 수 없습니다."
    return {"total_equity": yd.total_equity or 0, "operating_income": yd.operating_income or 0}, None


def get_company_market_cap(corp_code: str) -> int | None:
    """Company.market_cap 단순 조회(없거나 기업 없으면 None)."""
    CompanyModel = django_apps.get_model('apps', 'Company')
    try:
        return getattr(CompanyModel.objects.get(corp_code=corp_code), "market_cap", None)
    except CompanyModel.DoesNotExist:
        return None


def get_company_market_cap_info(corp_code: str) -> dict | None:
    """시총 조회 뷰용. 기업 없으면 None, 있으면 {"market_cap", "market_cap_updated_at"(iso|None)}."""
    CompanyModel = django_apps.get_model('apps', 'Company')
    try:
        company = CompanyModel.objects.get(corp_code=corp_code)
    except CompanyModel.DoesNotExist:
        return None
    updated = getattr(company, "market_cap_updated_at", None)
    return {
        "market_cap": getattr(company, "market_cap", None),
        "market_cap_updated_at": updated.isoformat() if updated else None,
    }


def get_annual_report_info(corp_code: str) -> dict | None:
    """사업보고서 링크 뷰용. 기업 없으면 None, 있으면 {"rcept_no", "year"}(rcept_no None 가능)."""
    CompanyModel = django_apps.get_model('apps', 'Company')
    try:
        company = CompanyModel.objects.get(corp_code=corp_code)
    except CompanyModel.DoesNotExist:
        return None
    return {
        "rcept_no": company.latest_annual_rcept_no,
        "year": company.latest_annual_report_year,
    }


def recompute_and_save_ev_ic(corp_code: str, market_cap: int | None,
                             target_year: int | None = None) -> list[dict] | None:
    """
    연도별 EV/IC 재계산 후 저장. 연간 데이터 없으면 None.

    계산은 IndicatorCalculator.compute_ic_ev로 단일화(T7). 저장은 한 트랜잭션 +
    쓰기 락/재시도(T9). 계산(읽기)은 락 밖, 쓰기만 _do로 감싸 재시도 멱등 보장.
    """
    from apps.service.calculator import IndicatorCalculator
    from apps.models import YearlyFinancialDataObject

    YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
    yearly_list = list(
        YearlyFinancialDataModel.objects.filter(company_id=corp_code).order_by("year")
    )
    if not yearly_list:
        return None
    if target_year is not None:
        yearly_list = [yd for yd in yearly_list if yd.year == target_year]

    to_save = []
    results = []
    for yd in yearly_list:
        obj = YearlyFinancialDataObject(yd.year)
        obj.equity = yd.total_equity or 0
        obj.interest_bearing_debt = yd.interest_bearing_debt or 0
        obj.cash_and_cash_equivalents = getattr(yd, "cash_and_cash_equivalents", None) or 0
        obj.noncontrolling_interest = getattr(yd, "noncontrolling_interest", None) or 0

        ic, ev = IndicatorCalculator.compute_ic_ev(obj, market_cap)
        yd.invested_capital = ic
        yd.ev = ev
        to_save.append(yd)

        ev_over_ic = (ev / ic) if (ev is not None and ic and ic != 0) else None
        results.append({
            "year": yd.year,
            "ev": ev,
            "invested_capital": ic,
            "roic": yd.roic,
            "wacc": yd.wacc,
            "ev_over_ic": ev_over_ic,
        })

    def _do():
        with transaction.atomic():
            for yd in to_save:
                yd.save(update_fields=["invested_capital", "ev"])

    run_with_write_lock_retry(_do)
    return results


def nullify_uncomputed_indicators() -> int:
    """
    DB의 YearlyFinancialData 중 미계산 행(roic=0.0 AND wacc=0.0)의 roic·wacc·fcf를 None으로 갱신.

    선택 기준: roic=0.0 AND wacc=0.0 이중 조건.
    - 진짜 계산된 roic=0.0·wacc≠0 행은 보존(방어적 이중조건).
    - 런타임/테스트용. 데이터 마이그레이션(0022)은 동일 로직을 historical 모델로 self-contained
      재현하므로 이 함수를 import하지 않는다.

    한계(degenerate, 라이브 0건): total_equity=0(완전자본잠식) + interest_expense=0 +
    interest_bearing_debt>0 + operating_income=0 인 행은 calculate_roic/calculate_wacc가
    둘 다 정확히 0.0을 내므로 실측인데도 정리 대상이 되어 fcf까지 소실될 수 있다.
    현실 회사에선 자본잠식+무이자비용+영업이익0이 동시 성립해야 해 극히 드물고 현 DB엔 0건.

    Returns:
        갱신된 행 수 (int)
    """
    YearlyFinancialDataModel = django_apps.get_model("apps", "YearlyFinancialData")
    count = [0]

    def _do():
        with transaction.atomic():
            updated = YearlyFinancialDataModel.objects.filter(
                roic=0.0, wacc=0.0
            ).update(roic=None, wacc=None, fcf=None)
            count[0] = updated

    run_with_write_lock_retry(_do)
    return count[0]


def rank_passed_companies() -> dict:
    """
    통과기업(passed_all_filters=True & not passed_second_filter=False) 크로스섹셔널 랭킹.

    각 회사의 roic IS NOT NULL인 가장 최근 연도를 대표 스냅샷으로 축값 3개 추출:
      quality = roic - wacc (둘 중 하나라도 None이면 None)
      price   = ev / invested_capital (ev None 또는 ic None/0/음수면 None)
      growth  = sustainable_growth (None 가능)
    roic 있는 연도가 없으면 quality/price/growth 모두 None → 모든 축 최하위.

    N+1 방지: 통과기업의 YearlyFinancialData를 한 번에 로드 후 파이썬에서 회사별 선별.

    Returns:
        dict[corp_code] -> {'rank', 'score', 'rank_quality', 'rank_price', 'rank_growth'}
    """
    from apps.service.ranking import rank_companies

    CompanyModel = django_apps.get_model("apps", "Company")
    YearlyFinancialDataModel = django_apps.get_model("apps", "YearlyFinancialData")

    companies = list(
        CompanyModel.objects.filter(passed_all_filters=True).exclude(
            passed_second_filter=False
        )
    )
    if not companies:
        return {}

    corp_codes = [c.corp_code for c in companies]

    # 통과기업의 모든 연간 데이터 일괄 로드 (N+1 방지): (company_id, year 내림차순)
    yearly_rows = list(
        YearlyFinancialDataModel.objects.filter(
            company_id__in=corp_codes
        ).order_by("company_id", "-year")
    )

    # corp_code → roic IS NOT NULL인 가장 최근 연도 (정렬이 이미 내림차순이므로 첫 번째 hit)
    rep_map: dict = {}
    for yd in yearly_rows:
        code = yd.company_id
        if code not in rep_map and yd.roic is not None:
            rep_map[code] = yd

    def _quality(yd):
        if yd is None or yd.roic is None or yd.wacc is None:
            return None
        return yd.roic - yd.wacc

    def _price(yd):
        if yd is None or yd.ev is None:
            return None
        ic = getattr(yd, "invested_capital", None)
        # ic<=0(투하자본 0/음수: cash>equity+debt 등 비정상 자본구조)이면 price 의미 없음 → None.
        # 음수 ic는 ev/ic 부호를 뒤집어 거짓 바겐을 가격축 최상위로 올리므로 반드시 배제.
        if ic is None or ic <= 0:
            return None
        return yd.ev / ic

    def _growth(yd):
        if yd is None:
            return None
        return getattr(yd, "sustainable_growth", None)

    ranking_input = []
    for c in companies:
        yd = rep_map.get(c.corp_code)
        ranking_input.append({
            "corp_code": c.corp_code,
            "quality": _quality(yd),
            "price": _price(yd),
            "growth": _growth(yd),
        })

    ranked = rank_companies(ranking_input)

    return {
        r["corp_code"]: {
            "rank": r["rank"],
            "score": r["score"],
            "rank_quality": r["rank_quality"],
            "rank_price": r["rank_price"],
            "rank_growth": r["rank_growth"],
        }
        for r in ranked
    }


def query_passed_companies(page: int, page_size: int) -> dict:
    """
    1차 필터 통과(2차 미통과만 제외) 기업 목록 페이지네이션.
    {"companies": [{corp_code, company_name, rank, score, rank_quality, rank_price, rank_growth}],
     "total", "page", "page_size", "total_pages", "last_updated"(iso|None)} 반환.
    rank 오름차순(동률 시 company_name 보조정렬). 종목코드 보강은 뷰에서.

    성능 한계(통과기업 수가 적은 현재는 무해): 페이지마다 rank_passed_companies()를 호출해
    전 통과기업 YearlyFinancialData를 전수 재로드하고, rank_companies는 축당 O(N²) 경쟁순위를
    매긴다. 통과기업이 수천으로 늘면 페이지당 재계산 비용이 커지므로 그때 캐싱(요청·짧은 TTL)이 필요.
    """
    import math
    from django.db.models import Max

    CompanyModel = django_apps.get_model("apps", "Company")
    qs = CompanyModel.objects.filter(passed_all_filters=True).exclude(
        passed_second_filter=False
    )

    total = qs.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    if page > total_pages and total_pages > 0:
        page = total_pages

    # 랭킹 맵 조회 후 파이썬에서 rank 오름차순 정렬 (DB ORDER BY 대체)
    rank_map = rank_passed_companies()
    all_companies = list(qs)
    all_companies.sort(
        key=lambda c: (
            rank_map.get(c.corp_code, {}).get("rank") or float("inf"),
            c.company_name or "",
        )
    )

    start_idx = (page - 1) * page_size
    page_slice = all_companies[start_idx: start_idx + page_size]

    companies = []
    for c in page_slice:
        r = rank_map.get(c.corp_code, {})
        companies.append({
            "corp_code": c.corp_code,
            "company_name": c.company_name or "",
            "rank": r.get("rank"),
            "score": r.get("score"),
            "rank_quality": r.get("rank_quality"),
            "rank_price": r.get("rank_price"),
            "rank_growth": r.get("rank_growth"),
        })

    last_updated = None
    if total > 0:
        agg = qs.aggregate(Max("updated_at"))
        if agg.get("updated_at__max"):
            last_updated = agg["updated_at__max"].isoformat()

    return {
        "companies": companies,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "last_updated": last_updated,
    }


def search_companies_in_db(query: str, limit: int) -> list[dict]:
    """기업명 부분일치 + 종목코드(6)/기업번호(8) 정확일치 검색. [{corp_code, company_name}]."""
    from django.db.models import Q
    from apps.service.corp_code import resolve_corp_code

    CompanyModel = django_apps.get_model("apps", "Company")
    q_filter = Q(company_name__icontains=query)
    if query.isdigit():
        if len(query) == 8:
            q_filter |= Q(corp_code=query)
        elif len(query) == 6:
            resolved, _ = resolve_corp_code(query)
            if resolved:
                q_filter |= Q(corp_code=resolved)

    return [
        {"corp_code": c.corp_code, "company_name": c.company_name or ""}
        for c in CompanyModel.objects.filter(q_filter)[:limit]
    ]


# ──────────────────────────────────────────────────────────────────
# 즐겨찾기(Favorite/FavoriteGroup) DB 접근: api_favorites 뷰 전용.
# 동작 동등 유지를 위해 기존 favorites 경로에 없던 쓰기 락은 추가하지 않음.
# ──────────────────────────────────────────────────────────────────

def get_company_by_corp_code(corp_code: str):
    """corp_code로 Company 조회. 없으면 None."""
    CompanyModel = django_apps.get_model("apps", "Company")
    try:
        return CompanyModel.objects.get(corp_code=corp_code)
    except CompanyModel.DoesNotExist:
        return None


def get_favorite_groups_with_favorites():
    """그룹(name 오름차순) + 소속 즐겨찾기(company prefetch, company_name 정렬) 쿼리셋."""
    from django.db.models import Prefetch

    FavoriteGroupModel = django_apps.get_model("apps", "FavoriteGroup")
    FavoriteModel = django_apps.get_model("apps", "Favorite")
    return FavoriteGroupModel.objects.prefetch_related(
        Prefetch(
            "favorites",
            queryset=FavoriteModel.objects.select_related("company").order_by(
                "company__company_name"
            ),
        )
    ).order_by("name")


def get_all_favorite_groups():
    """전체 즐겨찾기 그룹 (name 오름차순) 쿼리셋."""
    FavoriteGroupModel = django_apps.get_model("apps", "FavoriteGroup")
    return FavoriteGroupModel.objects.all().order_by("name")


def get_favorite_group_by_id(group_id):
    """그룹 id로 FavoriteGroup 조회. 없으면 None."""
    FavoriteGroupModel = django_apps.get_model("apps", "FavoriteGroup")
    try:
        return FavoriteGroupModel.objects.get(id=group_id)
    except FavoriteGroupModel.DoesNotExist:
        return None


def favorite_group_name_exists(name: str, exclude_id=None) -> bool:
    """같은 이름의 그룹이 존재하는지. exclude_id 지정 시 그 id는 제외(rename용)."""
    FavoriteGroupModel = django_apps.get_model("apps", "FavoriteGroup")
    qs = FavoriteGroupModel.objects.filter(name=name)
    if exclude_id is not None:
        qs = qs.exclude(id=exclude_id)
    return qs.exists()


def create_favorite_group(name: str):
    """이름으로 FavoriteGroup 생성 후 반환."""
    FavoriteGroupModel = django_apps.get_model("apps", "FavoriteGroup")
    return FavoriteGroupModel.objects.create(name=name)


def rename_favorite_group(group, name: str):
    """그룹 이름 변경 후 저장."""
    group.name = name
    group.save()
    return group


def delete_favorite_group(group) -> None:
    """그룹 삭제(FK cascade로 소속 즐겨찾기도 삭제)."""
    group.delete()


def get_favorite_by_id(favorite_id):
    """즐겨찾기 id로 Favorite 조회. 없으면 None."""
    FavoriteModel = django_apps.get_model("apps", "Favorite")
    try:
        return FavoriteModel.objects.get(id=favorite_id)
    except FavoriteModel.DoesNotExist:
        return None


def get_or_create_favorite(group, company):
    """(group, company) 즐겨찾기 get_or_create. (favorite, created) 반환."""
    FavoriteModel = django_apps.get_model("apps", "Favorite")
    return FavoriteModel.objects.get_or_create(
        group=group, company=company, defaults={}
    )


def favorite_exists_in_group(group, company) -> bool:
    """해당 그룹에 같은 기업의 즐겨찾기가 존재하는지."""
    FavoriteModel = django_apps.get_model("apps", "Favorite")
    return FavoriteModel.objects.filter(group=group, company=company).exists()


def move_favorite_to_group(favorite, group):
    """즐겨찾기의 그룹 변경 후 저장."""
    favorite.group = group
    favorite.save()
    return favorite


def delete_favorite(favorite) -> None:
    """단일 즐겨찾기 삭제."""
    favorite.delete()


def delete_favorites_by_company(company) -> int:
    """해당 기업의 모든 즐겨찾기 삭제. 삭제된 건수 반환."""
    FavoriteModel = django_apps.get_model("apps", "Favorite")
    deleted_count, _ = FavoriteModel.objects.filter(company=company).delete()
    return deleted_count
