"""
URL configuration for config project.
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from apps.companies import views as companies_views

urlpatterns = [
    path('', RedirectView.as_view(url='/companies/', permanent=False), name='index'),
    path('admin/', admin.site.urls),
    path('api/dart/', include('apps.dart.urls')),
    path('api/ecos/', include('apps.ecos.urls')),
    path('companies/', include('apps.companies.urls')),
    path('api/companies/', include([
        # 고정 경로 (구체적 패턴 먼저)
        path('passed/', companies_views.get_passed_companies, name='get_passed_companies'),
        path('search/', companies_views.search_companies, name='search_companies'),
        path('favorites/', companies_views.get_favorites, name='get_favorites'),
        path('favorites/<int:favorite_id>/group/', companies_views.change_favorite_group, name='change_favorite_group'),
        path('favorites/<int:favorite_id>/', companies_views.favorite_detail, name='favorite_detail'),
        path('favorite-groups/', companies_views.favorite_groups, name='favorite_groups'),
        path('favorite-groups/<int:group_id>/', companies_views.favorite_group_detail, name='favorite_group_detail'),
        # 기업 단건 (corp_code 경로 - 위 패턴에 안 걸리면 여기서 매칭)
        path('<str:corp_code>/financial-data/', companies_views.get_financial_data, name='get_financial_data'),
        path('<str:corp_code>/calculator-data/', companies_views.get_calculator_data, name='get_calculator_data'),
        path('<str:corp_code>/annual-report-link/', companies_views.get_annual_report_link, name='get_annual_report_link'),
        path('<str:corp_code>/memo/', companies_views.save_memo, name='save_memo'),
        path('<str:corp_code>/parse-paste/', companies_views.parse_and_calculate, name='parse_and_calculate'),
        path('<str:corp_code>/calculated-indicators/', companies_views.save_calculated_indicators, name='save_calculated_indicators'),
        path('<str:corp_code>/favorites/', companies_views.favorite, name='favorite'),
        path('<str:corp_code>/quarterly-reports/collect/', companies_views.collect_quarterly_reports, name='collect_quarterly_reports'),
        path('<str:corp_code>/quarterly-data/', companies_views.get_quarterly_financial_data, name='get_quarterly_financial_data'),
    ])),
]

