"""
기업 API: 재무/계산기/분기/메모
"""
import logging
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

from apps.service.db import (
    load_company_from_db,
    upsert_company_memo,
    get_calculator_year_data,
    get_company_market_cap,
    get_company_market_cap_info,
    get_annual_report_info,
    recompute_and_save_ev_ic,
)
from apps.service.bond_yield import get_bond_yield_5y
from apps.service.corp_code import resolve_corp_code, get_stock_code_by_corp_code


@api_view(["GET"])
def get_financial_data(request, corp_code):
    """
    기업 재무 데이터 조회 API
    GET /api/companies/{corp_code}/financial-data/
    """
    try:
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

        # 시가총액은 수집 시점(eager) + 일별 배치(fetch_krx_daily)에서 갱신하므로
        # 상세 조회 시엔 DB 저장값만 읽는다. (조회마다 KRX 스냅샷 재파싱하던 lazy 경로 제거)

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

        data, db_err = get_calculator_year_data(corp_code, year)
        if db_err:
            return Response({"error": db_err}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "corp_code": corp_code,
                "year": year,
                "total_equity": data["total_equity"],
                "operating_income": data["operating_income"],
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
        resolved, err = resolve_corp_code(corp_code)
        if err:
            return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
        corp_code = resolved

        memo = request.data.get("memo", "")
        return Response(
            upsert_company_memo(corp_code, memo),
            status=status.HTTP_200_OK,
        )

    except Exception as e:
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

    from apps.service.krx_client import fetch_and_save_company_market_cap, get_snapshot_row_by_isu_cd

    if get_company_market_cap_info(corp_code) is None:
        return Response(
            {"error": "기업을 찾을 수 없습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    market_cap = fetch_and_save_company_market_cap(corp_code)
    info = get_company_market_cap_info(corp_code)  # KRX 갱신 후 최신값
    if market_cap is None:
        market_cap = info["market_cap"]

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
        "market_cap_updated_at": info["market_cap_updated_at"],
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
        resolved, err = resolve_corp_code(corp_code)
        if err:
            return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
        corp_code = resolved

        market_cap_raw = request.data.get("market_cap")
        market_cap = int(market_cap_raw) if market_cap_raw is not None else None
        if market_cap is None:
            from apps.service.krx_client import fetch_and_save_company_market_cap
            market_cap = fetch_and_save_company_market_cap(corp_code)
        if market_cap is None:
            market_cap = get_company_market_cap(corp_code)

        target_year = request.data.get("year")
        if target_year is not None:
            target_year = int(target_year)

        results = recompute_and_save_ev_ic(corp_code, market_cap, target_year)
        if results is None:
            return Response(
                {"error": "해당 기업의 연도별 재무 데이터가 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

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
        resolved, err = resolve_corp_code(corp_code)
        if err:
            return Response({"error": err}, status=status.HTTP_404_NOT_FOUND)
        corp_code = resolved

        info = get_annual_report_info(corp_code)
        if info is None:
            return Response(
                {"error": "기업을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        rcept_no = info["rcept_no"]
        year = info["year"]

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
