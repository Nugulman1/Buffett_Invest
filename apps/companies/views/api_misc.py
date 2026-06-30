"""
기업 API: passed, search
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.service.corp_code import get_stock_code_by_corp_code
from apps.service.db import query_passed_companies, search_companies_in_db


@api_view(["GET"])
def get_passed_companies(request):
    """
    필터 통과 기업 목록 조회 API. 1차 필터 통과 기업을 노출하며,
    상세에서 2차 평가 후 미통과한 기업만 제외 (2차 미평가/통과는 노출).
    GET /api/companies/passed/?page=1&page_size=10
    """
    page = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 10))

    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10

    result = query_passed_companies(page, page_size)
    # 종목코드 보강(corp_code 서비스, ORM 아님)은 표현 레이어에서.
    result["companies"] = [
        {
            "stock_code": get_stock_code_by_corp_code(c["corp_code"]) or "",
            "company_name": c["company_name"],
            "corp_code": c["corp_code"],
            "rank": c.get("rank"),
            "score": c.get("score"),
            "rank_quality": c.get("rank_quality"),
            "rank_price": c.get("rank_price"),
            "rank_growth": c.get("rank_growth"),
        }
        for c in result["companies"]
    ]
    return Response(result)


@api_view(["GET"])
def search_companies(request):
    """
    기업 검색 API (기업명, 종목코드 6자리, 기업번호 8자리)
    GET /api/companies/search/?q=검색어&limit=10
    """
    search_query = request.GET.get("q", "").strip()
    limit = int(request.GET.get("limit", 10))

    if not search_query:
        return Response({"companies": [], "total": 0})

    results = search_companies_in_db(search_query, limit)
    return Response({"companies": results, "total": len(results)})
