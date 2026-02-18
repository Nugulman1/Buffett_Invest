"""
기업 뷰 (페이지 + API)

Re-export for `from apps.companies import views` / `config.urls` usage.
"""
from .pages import company_list, company_detail, calculator
from .api_misc import get_passed_companies, search_companies
from .api_financial import (
    get_financial_data,
    get_calculator_data,
    save_memo,
    parse_and_calculate,
    calculate_ev_ic,
    get_annual_report_link,
    get_market_cap,
    collect_quarterly_reports,
    get_quarterly_financial_data,
)
from .api_favorites import (
    _get_favorite_models,
    get_favorites,
    favorite,
    favorite_detail,
    change_favorite_group,
    favorite_groups,
    favorite_group_detail,
)

__all__ = [
    "company_list",
    "company_detail",
    "calculator",
    "get_passed_companies",
    "search_companies",
    "get_financial_data",
    "get_calculator_data",
    "save_memo",
    "parse_and_calculate",
    "calculate_ev_ic",
    "get_annual_report_link",
    "get_market_cap",
    "collect_quarterly_reports",
    "get_quarterly_financial_data",
    "_get_favorite_models",
    "get_favorites",
    "favorite",
    "favorite_detail",
    "change_favorite_group",
    "favorite_groups",
    "favorite_group_detail",
]
