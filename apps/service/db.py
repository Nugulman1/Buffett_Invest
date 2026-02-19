"""
DB 레이어: 분기보고서 저장/조회, 기업·after_date 조회, 연간 Company 저장/조회

Companies 뷰는 이 모듈과 DART 서비스만 호출하고, 직접 ORM 사용하지 않음.
"""
import threading

from django.apps import apps as django_apps
from django.utils import timezone
from django.db import transaction

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
        company_data.filter_revenue_cagr = company.filter_revenue_cagr
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
            yearly_data_obj.fcf = yearly_data_db.fcf
            yearly_data_obj.roic = yearly_data_db.roic
            yearly_data_obj.wacc = yearly_data_db.wacc
            yearly_data_obj.ev = getattr(yearly_data_db, 'ev', None)
            yearly_data_obj.invested_capital = getattr(yearly_data_db, 'invested_capital', None)

            company_data.yearly_data.append(yearly_data_obj)

        return (company_data, company)

    except CompanyModel.DoesNotExist:
        return (None, None)


# 병렬 수집 시 SQLite 쓰기 충돌 방지용 락
db_write_lock = threading.Lock()


def save_company_to_db(company_data: CompanyFinancialObject) -> None:
    """
    CompanyFinancialObject를 Django 모델로 변환하여 DB에 저장

    트랜잭션으로 원자성 보장: Company와 YearlyFinancialData 저장이 모두 성공하거나 모두 실패.
    병렬 수집 시 한 번에 한 스레드만 쓰기하도록 락 사용.

    Args:
        company_data: CompanyFinancialObject 객체
    """
    CompanyModel = django_apps.get_model('apps', 'Company')
    YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
    now = timezone.now()

    with db_write_lock:
        with transaction.atomic():
            company, created = CompanyModel.objects.update_or_create(
                corp_code=company_data.corp_code,
                defaults={
                    'company_name': company_data.company_name,
                    'last_collected_at': now,
                    'passed_all_filters': company_data.passed_all_filters,
                    'filter_operating_income': company_data.filter_operating_income,
                    'filter_net_income': company_data.filter_net_income,
                    'filter_revenue_cagr': company_data.filter_revenue_cagr,
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
                        'capital_stock': getattr(yearly_data, 'capital_stock', None),
                        'retained_earnings': getattr(yearly_data, 'retained_earnings', None),
                        'profit_before_tax': getattr(yearly_data, 'profit_before_tax', None),
                        'dividend_paid': getattr(yearly_data, 'dividend_paid', None),
                        'ev': getattr(yearly_data, 'ev', None),
                        'invested_capital': getattr(yearly_data, 'invested_capital', None),
                    }
                )

            # yearly_indicators는 함수 내 임시 데이터(ROE 등 채움용). DB에 저장하지 않음.
