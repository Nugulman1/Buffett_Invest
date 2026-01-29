"""
기업 API: 재무/계산기/분기/메모
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from apps.service.orchestrator import DataOrchestrator
from apps.service.db import should_collect_company_from_company, load_company_from_db
from apps.service.bond_yield import get_bond_yield_5y
from apps.service.corp_code import resolve_corp_code, get_stock_code_by_corp_code
from apps.service.passed_json import save_passed_companies_json


def _process_single_year_indicators(year_data, corp_code, company):
    """단일 년도 지표 계산 및 저장."""
    from django.apps import apps as django_apps
    from django.conf import settings
    from apps.service.calculator import IndicatorCalculator
    from apps.models import YearlyFinancialDataObject

    YearlyFinancialDataModel = django_apps.get_model("apps", "YearlyFinancialData")
    year = year_data.get("year")
    if not year:
        raise ValueError("year 필드가 필요합니다.")

    try:
        yearly_data_db = YearlyFinancialDataModel.objects.get(
            company=company, year=year
        )
    except YearlyFinancialDataModel.DoesNotExist:
        raise YearlyFinancialDataModel.DoesNotExist(
            f"{year}년도 데이터를 찾을 수 없습니다. 먼저 재무 데이터를 수집해주세요."
        )

    yearly_data_obj = YearlyFinancialDataObject(year=year)
    yearly_data_obj.cfo = year_data.get("cfo", 0) or 0
    yearly_data_obj.tangible_asset_acquisition = (
        year_data.get("tangible_asset_acquisition", 0) or 0
    )
    yearly_data_obj.intangible_asset_acquisition = (
        year_data.get("intangible_asset_acquisition", 0) or 0
    )
    yearly_data_obj.operating_income = year_data.get("operating_income", 0) or 0
    yearly_data_obj.equity = year_data.get("equity", 0) or 0
    yearly_data_obj.interest_bearing_debt = (
        year_data.get("interest_bearing_debt", 0) or 0
    )
    yearly_data_obj.cash_and_cash_equivalents = (
        year_data.get("cash_and_cash_equivalents", 0) or 0
    )
    yearly_data_obj.interest_expense = year_data.get("interest_expense", 0) or 0

    defaults = settings.CALCULATOR_DEFAULTS
    tax_rate = float(year_data.get("tax_rate", defaults["TAX_RATE"])) / 100.0
    bond_yield = float(year_data.get("bond_yield", 3.5))
    equity_risk_premium = float(year_data.get("equity_risk_premium", defaults["EQUITY_RISK_PREMIUM"]))

    fcf = IndicatorCalculator.calculate_fcf(yearly_data_obj)
    roic = IndicatorCalculator.calculate_roic(yearly_data_obj, tax_rate)
    wacc = IndicatorCalculator.calculate_wacc(
        yearly_data_obj, bond_yield, tax_rate, equity_risk_premium
    )

    yearly_data_db.fcf = fcf
    yearly_data_db.roic = roic
    yearly_data_db.wacc = wacc
    yearly_data_db.save()

    return {
        "corp_code": corp_code,
        "year": year,
        "fcf": fcf,
        "roic": roic,
        "wacc": wacc,
    }


@api_view(["GET"])
def get_financial_data(request, corp_code):
    """
    기업 재무 데이터 조회 API
    GET /api/companies/{corp_code}/financial-data/
    """
    try:
        from django.apps import apps as django_apps

        CompanyModel = django_apps.get_model("apps", "Company")

        resolved, err = resolve_corp_code(corp_code)
        if err:
            return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
        corp_code = resolved

        company_data, company = load_company_from_db(corp_code)
        if (
            company_data
            and company_data.yearly_data
            and company
            and not should_collect_company_from_company(company)
        ):
            memo = company.memo
            memo_updated_at = (
                company.memo_updated_at.isoformat()
                if company.memo_updated_at
                else None
            )
            data = {
                "corp_code": company_data.corp_code,
                "company_name": company_data.company_name,
                "bond_yield_5y": get_bond_yield_5y(),
                "passed_all_filters": company_data.passed_all_filters,
                "filter_operating_income": company_data.filter_operating_income,
                "filter_net_income": company_data.filter_net_income,
                "filter_revenue_cagr": company_data.filter_revenue_cagr,
                "filter_operating_margin": company_data.filter_operating_margin,
                "filter_roe": company_data.filter_roe,
                "memo": memo,
                "memo_updated_at": memo_updated_at,
                "yearly_data": [
                    {
                        "year": yd.year,
                        "revenue": yd.revenue,
                        "operating_income": yd.operating_income,
                        "net_income": yd.net_income,
                        "total_assets": yd.total_assets,
                        "total_equity": yd.total_equity,
                        "operating_margin": yd.operating_margin,
                        "roe": yd.roe,
                        "fcf": yd.fcf,
                        "roic": yd.roic,
                        "wacc": yd.wacc,
                    }
                    for yd in company_data.yearly_data
                ],
            }
            return Response(data, status=status.HTTP_200_OK)

        orchestrator = DataOrchestrator()
        company_data = orchestrator.collect_company_data(corp_code)

        company_data_from_db, company_from_db = load_company_from_db(corp_code)
        if company_data_from_db:
            if company_data_from_db.passed_all_filters:
                stock_code = get_stock_code_by_corp_code(corp_code)
                if stock_code:
                    save_passed_companies_json(
                        stock_code,
                        company_data_from_db.company_name or "",
                        corp_code,
                    )
            if company_from_db:
                memo = company_from_db.memo
                memo_updated_at = (
                    company_from_db.memo_updated_at.isoformat()
                    if company_from_db.memo_updated_at
                    else None
                )
            else:
                memo = None
                memo_updated_at = None

            data = {
                "corp_code": company_data_from_db.corp_code,
                "company_name": company_data_from_db.company_name,
                "bond_yield_5y": get_bond_yield_5y(),
                "passed_all_filters": company_data_from_db.passed_all_filters,
                "filter_operating_income": company_data_from_db.filter_operating_income,
                "filter_net_income": company_data_from_db.filter_net_income,
                "filter_revenue_cagr": company_data_from_db.filter_revenue_cagr,
                "filter_operating_margin": company_data_from_db.filter_operating_margin,
                "filter_roe": company_data_from_db.filter_roe,
                "memo": memo,
                "memo_updated_at": memo_updated_at,
                "yearly_data": [
                    {
                        "year": yd.year,
                        "revenue": yd.revenue,
                        "operating_income": yd.operating_income,
                        "net_income": yd.net_income,
                        "total_assets": yd.total_assets,
                        "total_equity": yd.total_equity,
                        "operating_margin": yd.operating_margin,
                        "roe": yd.roe,
                        "fcf": yd.fcf,
                        "roic": yd.roic,
                        "wacc": yd.wacc,
                    }
                    for yd in company_data_from_db.yearly_data
                ],
            }
        else:
            try:
                company = CompanyModel.objects.get(corp_code=corp_code)
                memo = company.memo
                memo_updated_at = (
                    company.memo_updated_at.isoformat()
                    if company.memo_updated_at
                    else None
                )
            except CompanyModel.DoesNotExist:
                memo = None
                memo_updated_at = None

            data = {
                "corp_code": company_data.corp_code,
                "company_name": company_data.company_name,
                "bond_yield_5y": get_bond_yield_5y(),
                "passed_all_filters": company_data.passed_all_filters,
                "filter_operating_income": company_data.filter_operating_income,
                "filter_net_income": company_data.filter_net_income,
                "filter_revenue_cagr": company_data.filter_revenue_cagr,
                "filter_operating_margin": company_data.filter_operating_margin,
                "filter_roe": company_data.filter_roe,
                "memo": memo,
                "memo_updated_at": memo_updated_at,
                "yearly_data": [
                    {
                        "year": yd.year,
                        "revenue": yd.revenue,
                        "operating_income": yd.operating_income,
                        "net_income": yd.net_income,
                        "total_assets": yd.total_assets,
                        "total_equity": yd.total_equity,
                        "operating_margin": yd.operating_margin,
                        "roe": yd.roe,
                        "fcf": None,
                        "roic": None,
                        "wacc": None,
                    }
                    for yd in company_data.yearly_data
                ],
            }

        return Response(data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_calculator_data(request, corp_code):
    """
    계산기용 데이터 조회 API
    GET /api/companies/{corp_code}/calculator-data/?year=2023
    """
    try:
        from django.apps import apps as django_apps

        CompanyModel = django_apps.get_model("apps", "Company")
        YearlyFinancialDataModel = django_apps.get_model(
            "apps", "YearlyFinancialData"
        )

        year = request.query_params.get("year")
        if not year:
            return Response(
                {"error": "year 파라미터가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            year = int(year)
        except ValueError:
            return Response(
                {"error": "year는 정수여야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        resolved, err = resolve_corp_code(corp_code)
        if err:
            return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
        corp_code = resolved

        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
        except CompanyModel.DoesNotExist:
            return Response(
                {"error": f"기업코드 {corp_code}에 해당하는 데이터를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            yearly_data = YearlyFinancialDataModel.objects.get(
                company=company, year=year
            )
            total_equity = yearly_data.total_equity or 0
            operating_income = yearly_data.operating_income or 0
        except YearlyFinancialDataModel.DoesNotExist:
            return Response(
                {"error": f"{year}년 데이터를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "corp_code": corp_code,
                "year": year,
                "total_equity": total_equity,
                "operating_income": operating_income,
                "bond_yield_5y": get_bond_yield_5y(),
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def save_memo(request, corp_code):
    """
    기업 메모 저장 API
    POST /api/companies/{corp_code}/memo/
    """
    try:
        from django.apps import apps as django_apps
        from django.utils import timezone

        CompanyModel = django_apps.get_model("apps", "Company")

        resolved, err = resolve_corp_code(corp_code)
        if err:
            return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
        corp_code = resolved

        memo = request.data.get("memo", "")
        now = timezone.now()

        company, created = CompanyModel.objects.update_or_create(
            corp_code=corp_code,
            defaults={
                "memo": memo,
                "memo_updated_at": now if memo else None,
            },
        )

        return Response(
            {
                "corp_code": company.corp_code,
                "memo": company.memo,
                "memo_updated_at": (
                    company.memo_updated_at.isoformat()
                    if company.memo_updated_at
                    else None
                ),
                "created": created,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def save_calculated_indicators(request, corp_code):
    """
    계산 지표 저장 API
    POST /api/companies/{corp_code}/calculated-indicators/
    """
    try:
        from django.apps import apps as django_apps

        CompanyModel = django_apps.get_model("apps", "Company")
        YearlyFinancialDataModel = django_apps.get_model(
            "apps", "YearlyFinancialData"
        )

        resolved, err = resolve_corp_code(corp_code)
        if err:
            return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
        corp_code = resolved

        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
        except CompanyModel.DoesNotExist:
            return Response(
                {"error": f"기업을 찾을 수 없습니다. (corp_code: {corp_code})"},
                status=status.HTTP_404_NOT_FOUND,
            )

        data_list = (
            request.data
            if isinstance(request.data, list)
            else [request.data]
        )

        results = []
        errors = []

        for idx, year_data in enumerate(data_list):
            try:
                result = _process_single_year_indicators(
                    year_data, corp_code, company
                )
                results.append(result)
            except YearlyFinancialDataModel.DoesNotExist as e:
                errors.append(
                    {"index": idx, "year": year_data.get("year"), "error": str(e)}
                )
            except ValueError as e:
                errors.append(
                    {"index": idx, "year": year_data.get("year"), "error": str(e)}
                )
            except Exception as e:
                errors.append(
                    {"index": idx, "year": year_data.get("year"), "error": str(e)}
                )

        response_data = {
            "results": results,
            "success_count": len(results),
            "total_count": len(data_list),
        }
        if errors:
            response_data["errors"] = errors

        if not results:
            return Response(
                response_data,
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_annual_report_link(request, corp_code):
    """
    사업보고서 링크 조회 API
    GET /api/companies/{corp_code}/annual-report-link/
    """
    try:
        from django.apps import apps as django_apps

        CompanyModel = django_apps.get_model("apps", "Company")

        resolved, err = resolve_corp_code(corp_code)
        if err:
            return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
        corp_code = resolved

        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
        except CompanyModel.DoesNotExist:
            return Response(
                {"error": "기업을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        rcept_no = company.latest_annual_rcept_no
        year = company.latest_annual_report_year

        if not rcept_no:
            return Response(
                {
                    "error": "사업보고서를 찾을 수 없습니다. 재무 데이터를 먼저 수집해 주세요."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        dart_link = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        return Response(
            {"rcept_no": rcept_no, "year": year, "link": dart_link},
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def collect_quarterly_reports(request, corp_code):
    """
    최근 분기보고서 수집 API
    POST /api/companies/{corp_code}/quarterly-reports/collect/
    """
    try:
        from apps.service.dart import DartDataService
        from apps.service.db import (
            get_company_for_quarterly_collect,
            save_quarterly_financial_data,
        )

        resolved, err = resolve_corp_code(corp_code)
        if err:
            return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
        corp_code = resolved

        company, after_date_or_err = get_company_for_quarterly_collect(corp_code)
        if company is None:
            return Response(
                {"error": after_date_or_err},
                status=status.HTTP_404_NOT_FOUND,
            )
        after_date = after_date_or_err

        dart_service = DartDataService()
        quarterly_data_list = dart_service.collect_quarterly_data_for_save(
            corp_code, after_date
        )

        if not quarterly_data_list:
            return Response(
                {
                    "message": "최근 사업보고서 이후의 분기보고서가 없습니다.",
                    "collected_count": 0,
                },
                status=status.HTTP_200_OK,
            )

        collected_count = save_quarterly_financial_data(
            company, quarterly_data_list
        )

        return Response(
            {
                "message": f"{collected_count}개의 분기보고서를 수집했습니다.",
                "collected_count": collected_count,
                "quarterly_reports": [
                    {
                        "year": year,
                        "quarter": quarter,
                        "rcept_no": rcept_no,
                    }
                    for year, quarter, _, rcept_no, _ in quarterly_data_list
                ],
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_quarterly_financial_data(request, corp_code):
    """
    분기보고서 재무 데이터 조회 API
    GET /api/companies/{corp_code}/quarterly-data/
    """
    try:
        from apps.service.db import load_quarterly_financial_data

        resolved, err = resolve_corp_code(corp_code)
        if err:
            return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
        corp_code = resolved

        quarterly_data = load_quarterly_financial_data(corp_code)
        return Response(
            {"quarterly_data": quarterly_data},
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
