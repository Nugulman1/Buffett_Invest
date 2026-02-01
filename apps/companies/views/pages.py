"""
기업 페이지 뷰 (목록, 상세, 계산기)
"""
from django.shortcuts import render
from django.http import HttpResponseNotFound

from apps.service.corp_code import resolve_corp_code


def company_list(request):
    """
    기업 목록 조회 페이지 (메인 페이지)
    GET /companies/
    """
    return render(request, "companies/list.html")


def company_detail(request, corp_code):
    """
    기업 상세 정보 페이지
    GET /companies/{corp_code}/

    corp_code는 종목코드(6자리) 또는 기업번호(8자리)를 받을 수 있습니다.
    """
    resolved, err = resolve_corp_code(corp_code)
    if err:
        return HttpResponseNotFound(err)
    corp_code = resolved
    return render(request, "companies/detail.html", {"corp_code": corp_code})


def calculator(request):
    """
    재무 지표 계산기 페이지
    GET /companies/calculator/?corp_code=XXXXX (기업 상세에서만 진입)
    """
    from django.conf import settings
    from apps.service.bond_yield import get_bond_yield_5y

    bond_yield_5y = get_bond_yield_5y()
    bond_yield_default = round(bond_yield_5y * 100, 2) if bond_yield_5y else 3.5

    return render(
        request,
        "companies/calculator.html",
        {
            "calculator_defaults": settings.CALCULATOR_DEFAULTS,
            "bond_yield_default": bond_yield_default,
        },
    )
