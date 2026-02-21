"""
기업 API: 재무/계산기/분기/메모
"""
import logging
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

from apps.service.db import load_company_from_db
from apps.service.bond_yield import get_bond_yield_5y
from apps.service.corp_code import resolve_corp_code, get_stock_code_by_corp_code


def _refresh_second_filter_only(corp_code: str) -> None:
    """
    DB에 저장된 최근 3년 ROIC/WACC로 2차 필터만 재계산해 Company.passed_second_filter에 반영.
    KRX/EV/IC 갱신 없이 기업 조회·계산기 저장 후 2차 필터만 갱신할 때 사용.
    """
    from django.apps import apps as django_apps
    from apps.service.filter import CompanyFilter

    CompanyModel = django_apps.get_model("apps", "Company")
    try:
        company = CompanyModel.objects.get(corp_code=corp_code)
        company.passed_second_filter = CompanyFilter.check_second_filter(corp_code)
        company.save(update_fields=["passed_second_filter"])
    except CompanyModel.DoesNotExist:
        pass


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
        if not company_data:
            return Response(
                {"error": "기업 데이터를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        memo = company.memo if company else None
        memo_updated_at = (
            company.memo_updated_at.isoformat()
            if company and company.memo_updated_at
            else None
        )
        market_cap = getattr(company, "market_cap", None) if company else None
        market_cap_updated_at = (
            company.market_cap_updated_at.isoformat()
            if company and getattr(company, "market_cap_updated_at", None)
            else None
        )
        sorted_yearly = sorted(company_data.yearly_data, key=lambda x: x.year, reverse=True)
        consecutive_dividend_years = 0
        for yd in sorted_yearly:
            if yd.dividend_paid is None or yd.dividend_paid <= 0:
                break
            consecutive_dividend_years += 1
        data = {
            "corp_code": company_data.corp_code,
            "company_name": company_data.company_name,
            "bond_yield_5y": get_bond_yield_5y(),
            "market_cap": market_cap,
            "market_cap_updated_at": market_cap_updated_at,
            "passed_all_filters": company_data.passed_all_filters,
            "passed_second_filter": getattr(company, "passed_second_filter", None) if company else None,
            "consecutive_dividend_years": consecutive_dividend_years,
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
                    "selling_admin_expense_ratio": getattr(yd, "selling_admin_expense_ratio", None),
                    "roe": yd.roe,
                    "debt_ratio": getattr(yd, "debt_ratio", None),
                    "fcf": yd.fcf,
                    "roic": yd.roic,
                    "wacc": yd.wacc,
                    "ev": getattr(yd, "ev", None),
                    "invested_capital": getattr(yd, "invested_capital", None),
                    "dividend_paid": getattr(yd, "dividend_paid", None),
                    "dividend_payout_ratio": getattr(yd, "dividend_payout_ratio", None),
                    "interest_expense": getattr(yd, "interest_expense", None),
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
def parse_and_calculate(request, corp_code):
    """
    복붙 재무제표 파싱 및 FCF/ROIC/WACC 계산·저장 API
    POST /api/companies/{corp_code}/parse-paste/

    Request Body:
        balance_sheet: 연결 재무상태표 텍스트
        cash_flow: 연결 현금흐름표 텍스트
        tax_rate, bond_yield, equity_risk_premium: 선택 (기본값 사용)

    자본총계(equity)는 DB 기존 데이터 사용. 해당 연도 데이터가 없으면 해당 연도는 건너뜀.
    """
    try:
        from django.apps import apps as django_apps
        from django.conf import settings
        from apps.service.paste_parser import parse_balance_sheet, parse_cash_flow
        from apps.service.llm_extractor import extract_financial_indicators
        from apps.service.calculator import IndicatorCalculator
        from apps.models import YearlyFinancialDataObject

        CompanyModel = django_apps.get_model("apps", "Company")
        YearlyFinancialDataModel = django_apps.get_model("apps", "YearlyFinancialData")

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

        balance_sheet = (request.data.get("balance_sheet") or "").strip()
        cash_flow = (request.data.get("cash_flow") or "").strip()
        if not balance_sheet or not cash_flow:
            return Response(
                {"error": "balance_sheet와 cash_flow를 모두 입력해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        defaults = settings.CALCULATOR_DEFAULTS
        tax_rate_pct = float(request.data.get("tax_rate", defaults["TAX_RATE"]))
        bond_yield = float(request.data.get("bond_yield", 3.5))
        equity_risk_premium = float(
            request.data.get("equity_risk_premium", defaults["EQUITY_RISK_PREMIUM"])
        )
        tax_rate = tax_rate_pct / 100.0

        bs_result = parse_balance_sheet(balance_sheet)
        cf_result = parse_cash_flow(cash_flow)
        years = sorted(
            set(bs_result["years"]) | set(cf_result["years"]),
            reverse=True,
        )
        if not years:
            return Response(
                {"error": "연도를 추출할 수 없습니다. 텍스트에 2020~2029 형식이 있는지 확인해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not settings.OPENAI_API_KEY:
            return Response(
                {"error": "OPENAI_API_KEY가 설정되지 않았습니다. .env를 확인해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # EV 계산용 시가총액: 재무지표 계산 시점에 KRX에서 한 번 조회
        from apps.service.krx_client import fetch_and_save_company_market_cap
        fetch_and_save_company_market_cap(corp_code)
        company.refresh_from_db()
        market_cap = getattr(company, "market_cap", None)

        all_rows = bs_result["rows"] + cf_result["rows"]
        try:
            extracted = extract_financial_indicators(all_rows, years)
        except ValueError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("[parse_and_calculate] LLM 추출 실패: %s", e)
            return Response(
                {"error": f"지표 추출 실패: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        from apps.utils.format_ import format_amount_korean

        logger.info("=" * 60)
        logger.info("[parse_and_calculate] LLM 추출 지표 (수집 결과)")
        logger.info("=" * 60)
        for year in years:
            row = extracted.get(year, {})
            labels = row.get("_interest_bearing_debt_labels", [])
            logger.info(
                "  [%s년] cfo=%s, 유형자산취득=%s, 무형자산취득=%s, 기말현금=%s, 이자비용=%s, 이자부채=%s, 배당금지급=%s",
                year,
                format_amount_korean(row.get("cfo", 0) or 0),
                format_amount_korean(row.get("tangible_asset_acquisition", 0) or 0),
                format_amount_korean(row.get("intangible_asset_acquisition", 0) or 0),
                format_amount_korean(row.get("cash_and_cash_equivalents", 0) or 0),
                format_amount_korean(row.get("interest_expense", 0) or 0),
                format_amount_korean(row.get("interest_bearing_debt", 0) or 0),
                format_amount_korean(row.get("dividend_paid", 0) or 0),
            )
            if labels:
                logger.info("  [%s년] 이자부채 합산에 사용한 계정: %s", year, labels)
            breakdown = row.get("_interest_bearing_debt_breakdown", {})
            if breakdown:
                for label, val in breakdown.items():
                    try:
                        amt = int(val) if val is not None else 0
                        logger.info("    [이자부채 디버깅] %s -> %s", label, format_amount_korean(amt) if amt else "0")
                    except (TypeError, ValueError):
                        logger.info("    [이자부채 디버깅] %s -> %s", label, val)
        logger.info("=" * 60)

        results = []
        errors = []
        yearly_data_list = list(
            YearlyFinancialDataModel.objects.filter(company=company).order_by("-year")
        )
        db_by_year = {yd.year: yd for yd in yearly_data_list}

        for year in years:
            row = extracted.get(year, {})
            yearly_data_db = db_by_year.get(year)
            if not yearly_data_db:
                errors.append({"year": year, "error": "해당 연도 DB 데이터가 없습니다. 먼저 재무 데이터를 수집해주세요."})
                continue

            if yearly_data_db.operating_income is None or yearly_data_db.total_equity is None:
                yearly_data_db.fcf = None
                yearly_data_db.roic = None
                yearly_data_db.wacc = None
                yearly_data_db.ev = None
                yearly_data_db.invested_capital = None
                yearly_data_db.save()
                results.append({
                    "year": year,
                    "fcf": None,
                    "roic": None,
                    "wacc": None,
                    "ev": None,
                    "invested_capital": None,
                    "parsed_accounts": {k: v for k, v in row.items() if not k.startswith("_") and v},
                })
                continue

            interest_bearing_debt = row.get("interest_bearing_debt", 0) or 0

            yearly_data_obj = YearlyFinancialDataObject(year=year)
            yearly_data_obj.revenue = yearly_data_db.revenue or 0
            yearly_data_obj.operating_income = yearly_data_db.operating_income or 0
            yearly_data_obj.net_income = yearly_data_db.net_income or 0
            yearly_data_obj.total_assets = yearly_data_db.total_assets or 0
            yearly_data_obj.total_equity = yearly_data_db.total_equity or 0
            yearly_data_obj.equity = yearly_data_db.total_equity or 0
            yearly_data_obj.operating_margin = yearly_data_db.operating_margin or 0.0
            yearly_data_obj.roe = yearly_data_db.roe or 0.0
            yearly_data_obj.cfo = row.get("cfo", 0) or 0
            yearly_data_obj.tangible_asset_acquisition = row.get("tangible_asset_acquisition", 0) or 0
            yearly_data_obj.intangible_asset_acquisition = row.get("intangible_asset_acquisition", 0) or 0
            yearly_data_obj.cash_and_cash_equivalents = row.get("cash_and_cash_equivalents", 0) or 0
            yearly_data_obj.interest_bearing_debt = interest_bearing_debt
            yearly_data_obj.interest_expense = row.get("interest_expense", 0) or 0
            yearly_data_obj.noncontrolling_interest = row.get("noncontrolling_interest", 0) or 0

            fcf = IndicatorCalculator.calculate_fcf(yearly_data_obj)
            roic = IndicatorCalculator.calculate_roic(yearly_data_obj, tax_rate)
            wacc = IndicatorCalculator.calculate_wacc(
                yearly_data_obj, bond_yield, tax_rate, equity_risk_premium
            )

            # 계산 과정 콘솔 출력 (calculator 결과만 사용, 공식은 calculator.py 일원화)
            capex = yearly_data_obj.tangible_asset_acquisition + yearly_data_obj.intangible_asset_acquisition
            logger.info("")
            logger.info("[%s년] 계산 과정 (DB: 영업이익=%s, 자본=%s)",
                year,
                format_amount_korean(yearly_data_obj.operating_income),
                format_amount_korean(yearly_data_obj.equity),
            )
            logger.info("  FCF: CFO(%s) - |유형+무형취득(%s)| = %s",
                format_amount_korean(yearly_data_obj.cfo),
                format_amount_korean(capex),
                format_amount_korean(fcf),
            )
            logger.info("  ROIC: %.2f%%, WACC: %.2f%%", roic * 100, wacc * 100)

            dividend_val = row.get("dividend_paid")
            yearly_data_db.dividend_paid = (
                int(dividend_val) if dividend_val is not None and dividend_val != "" else None
            )
            interest_expense_val = row.get("interest_expense")
            yearly_data_db.interest_expense = (
                int(interest_expense_val) if interest_expense_val is not None and interest_expense_val != "" else None
            )
            yearly_data_db.interest_bearing_debt = interest_bearing_debt
            yearly_data_db.cash_and_cash_equivalents = yearly_data_obj.cash_and_cash_equivalents
            yearly_data_db.noncontrolling_interest = yearly_data_obj.noncontrolling_interest
            yearly_data_db.fcf = fcf
            yearly_data_db.roic = roic
            yearly_data_db.wacc = wacc
            dividend_payout_ratio = None
            if fcf and fcf > 0 and yearly_data_db.dividend_paid is not None and yearly_data_db.dividend_paid >= 0:
                dividend_payout_ratio = yearly_data_db.dividend_paid / fcf
            yearly_data_db.dividend_payout_ratio = dividend_payout_ratio

            # EV/IC: 이자부채·현금·비지배지분 등 추출 데이터 기준으로 계산 후 저장
            ic = IndicatorCalculator.calculate_invested_capital(yearly_data_obj)
            ev = (
                IndicatorCalculator.calculate_ev(
                    market_cap or 0,
                    yearly_data_obj.interest_bearing_debt,
                    yearly_data_obj.cash_and_cash_equivalents,
                    yearly_data_obj.noncontrolling_interest,
                )
                if market_cap is not None
                else None
            )
            yearly_data_db.invested_capital = ic
            yearly_data_db.ev = ev
            yearly_data_db.save()

            results.append({
                "year": year,
                "fcf": fcf,
                "roic": roic,
                "wacc": wacc,
                "ev": ev,
                "invested_capital": ic,
                "parsed_accounts": {k: v for k, v in row.items() if not k.startswith("_") and v},
            })

        logger.info("")
        logger.info("[parse_and_calculate] DB 저장 완료: %s개 연도", len(results))
        # 2차 필터만 DB 기준으로 갱신 (EV/IC는 위에서 재무지표 계산 시 함께 저장됨)
        _refresh_second_filter_only(corp_code)

        if not results:
            return Response(
                {
                    "success": False,
                    "results": [],
                    "errors": errors,
                    "error": "저장된 연도가 없습니다. 해당 기업의 재무 데이터를 먼저 수집해주세요.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "success": True,
                "results": results,
                "errors": errors if errors else None,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.exception("[parse_and_calculate] 오류: %s", e)
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_market_cap(request, corp_code):
    """
    시가총액 조회 API (KRX에서 조회 후 Company에 저장)
    GET /api/companies/{corp_code}/market-cap/
    """
    resolved, err = resolve_corp_code(corp_code)
    if err:
        return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
    corp_code = resolved

    from django.apps import apps as django_apps
    from apps.service.krx_client import fetch_and_save_company_market_cap, get_snapshot_row_by_isu_cd
    from apps.service.corp_code import get_stock_code_by_corp_code

    CompanyModel = django_apps.get_model("apps", "Company")
    try:
        company = CompanyModel.objects.get(corp_code=corp_code)
    except CompanyModel.DoesNotExist:
        return Response(
            {"error": "기업을 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    market_cap = fetch_and_save_company_market_cap(corp_code)
    company.refresh_from_db()
    if market_cap is None:
        market_cap = getattr(company, "market_cap", None)

    krx_daily = None
    stock_code = get_stock_code_by_corp_code(corp_code)
    if stock_code:
        row = get_snapshot_row_by_isu_cd(stock_code)
        if row:
            krx_daily = {
                "BAS_DD": row.get("BAS_DD"),
                "IDX_CLSS": row.get("MKT_NM"),
                "IDX_NM": row.get("ISU_NM"),
                "CLSPRC_IDX": row.get("TDD_CLSPRC"),
                "CMPPREVDD_IDX": row.get("CMPPREVDD_PRC"),
                "FLUC_RT": row.get("FLUC_RT"),
                "OPNPRC_IDX": row.get("TDD_OPNPRC"),
                "HGPRC_IDX": row.get("TDD_HGPRC"),
                "LWPRC_IDX": row.get("TDD_LWPRC"),
                "ACC_TRDVOL": row.get("ACC_TRDVOL"),
                "ACC_TRDVAL": row.get("ACC_TRDVAL"),
                "MKTCAP": row.get("MKTCAP"),
            }

    return Response({
        "market_cap": market_cap,
        "market_cap_updated_at": (
            company.market_cap_updated_at.isoformat()
            if getattr(company, "market_cap_updated_at", None) else None
        ),
        "krx_daily_data": krx_daily,
    })


@api_view(["POST"])
def calculate_ev_ic(request, corp_code):
    """
    EV·IC 계산 및 DB 저장 API
    POST /api/companies/{corp_code}/calculate-ev-ic/

    시가총액: body의 market_cap 우선, 없으면 KRX API로 조회 후 Company에 저장, 없으면 DB 저장값 사용.
    Request Body:
        market_cap: (선택) 시가총액(원). 없으면 KRX 조회 또는 DB 저장값 사용.
        year: (선택) 특정 연도만 계산. 없으면 재무 데이터 있는 모든 연도.
    """
    try:
        from django.apps import apps as django_apps
        from apps.service.calculator import IndicatorCalculator
        from apps.models import YearlyFinancialDataObject

        YearlyFinancialDataModel = django_apps.get_model("apps", "YearlyFinancialData")

        resolved, err = resolve_corp_code(corp_code)
        if err:
            return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
        corp_code = resolved

        yearly_list = list(
            YearlyFinancialDataModel.objects.filter(company_id=corp_code).order_by("year")
        )

        if not yearly_list:
            return Response(
                {"error": "해당 기업의 연도별 재무 데이터가 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        market_cap_raw = request.data.get("market_cap")
        market_cap = int(market_cap_raw) if market_cap_raw is not None else None
        if market_cap is None:
            from apps.service.krx_client import fetch_and_save_company_market_cap
            market_cap = fetch_and_save_company_market_cap(corp_code)
        if market_cap is None:
            CompanyModel = django_apps.get_model("apps", "Company")
            try:
                company = CompanyModel.objects.get(corp_code=corp_code)
                market_cap = getattr(company, "market_cap", None)
            except CompanyModel.DoesNotExist:
                pass
        target_year = request.data.get("year")
        if target_year is not None:
            target_year = int(target_year)
            yearly_list = [yd for yd in yearly_list if yd.year == target_year]

        results = []
        for yd in yearly_list:
            obj = YearlyFinancialDataObject(yd.year)
            obj.equity = yd.total_equity or 0
            obj.interest_bearing_debt = yd.interest_bearing_debt or 0
            obj.cash_and_cash_equivalents = getattr(yd, "cash_and_cash_equivalents", None) or 0
            nci = getattr(yd, "noncontrolling_interest", None) or 0

            ic = IndicatorCalculator.calculate_invested_capital(obj)
            ev = None
            if market_cap is not None:
                ev = IndicatorCalculator.calculate_ev(
                    market_cap,
                    obj.interest_bearing_debt,
                    obj.cash_and_cash_equivalents,
                    nci,
                )

            yd.invested_capital = ic
            yd.ev = ev
            yd.save(update_fields=["invested_capital", "ev"])

            roic = yd.roic
            wacc = yd.wacc
            ev_over_ic = (ev / ic) if (ev is not None and ic and ic != 0) else None
            results.append({
                "year": yd.year,
                "ev": ev,
                "invested_capital": ic,
                "roic": roic,
                "wacc": wacc,
                "ev_over_ic": ev_over_ic,
            })

        return Response(
            {"success": True, "results": results},
            status=status.HTTP_200_OK,
        )
    except Exception as e:
        logger.exception("[calculate_ev_ic] 오류: %s", e)
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

        result = get_company_for_quarterly_collect(corp_code)
        if result[0] is None:
            return Response(
                {"error": result[1]},
                status=status.HTTP_404_NOT_FOUND,
            )
        company = result[0]

        dart_service = DartDataService()
        quarterly_data_list = dart_service.collect_quarterly_data_for_save(corp_code)

        if not quarterly_data_list:
            return Response(
                {
                    "message": "분기보고서가 없습니다.",
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
