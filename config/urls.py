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
        path('<str:corp_code>/financial-data/', companies_views.get_financial_data, name='get_financial_data'),
        path('<str:corp_code>/calculator-data/', companies_views.get_calculator_data, name='get_calculator_data'),
        path('batch/', companies_views.batch_get_financial_data, name='batch_get_financial_data'),
        path('<str:corp_code>/annual-report-link/', companies_views.get_annual_report_link, name='get_annual_report_link'),
        path('<str:corp_code>/memo/', companies_views.save_memo, name='save_memo'),
        path('<str:corp_code>/calculated-indicators/', companies_views.save_calculated_indicators, name='save_calculated_indicators'),
        path('<str:corp_code>/manual-financial-data/', companies_views.save_manual_financial_data, name='save_manual_financial_data'),
    ])),
]

