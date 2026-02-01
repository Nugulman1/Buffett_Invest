"""
기업 API: passed, search
"""
import math

from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from apps.service.passed_json import load_passed_companies_json


@api_view(["GET"])
def get_passed_companies(request):
    """
    필터 통과 기업 목록 조회 API
    GET /api/companies/passed/?page=1&page_size=10
    """
    page = int(request.GET.get("page", 1))
    page_size = int(request.GET.get("page_size", 10))

    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10

    json_file = settings.BASE_DIR / "passed_filters_companies.json"
    data = load_passed_companies_json(json_file)

    all_companies = []
    for company in data.get("companies", []):
        all_companies.append({
            "stock_code": company.get("stock_code", ""),
            "company_name": company.get("company_name", ""),
            "corp_code": company.get("corp_code", ""),
        })

    total = len(all_companies)
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    if page > total_pages and total_pages > 0:
        page = total_pages

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    companies = all_companies[start_idx:end_idx]

    return Response({
        "companies": companies,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "last_updated": data.get("last_updated"),
    })


@api_view(["GET"])
def search_companies(request):
    """
    기업 검색 API (기업명, 종목코드 6자리, 기업번호 8자리)
    GET /api/companies/search/?q=검색어&limit=10
    """
    from django.apps import apps as django_apps
    from django.db.models import Q

    from apps.service.corp_code import resolve_corp_code

    CompanyModel = django_apps.get_model("apps", "Company")

    search_query = request.GET.get("q", "").strip()
    limit = int(request.GET.get("limit", 10))

    if not search_query:
        return Response({"companies": [], "total": 0})

    q_filter = Q(company_name__icontains=search_query)
    if search_query.isdigit():
        if len(search_query) == 8:
            q_filter |= Q(corp_code=search_query)
        elif len(search_query) == 6:
            resolved, _ = resolve_corp_code(search_query)
            if resolved:
                q_filter |= Q(corp_code=resolved)

    companies = CompanyModel.objects.filter(q_filter)[:limit]

    results = []
    for company in companies:
        results.append({
            "corp_code": company.corp_code,
            "company_name": company.company_name or "",
        })

    return Response({"companies": results, "total": len(results)})
