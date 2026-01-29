"""
기업 재무 데이터 URL 라우팅
"""
from django.urls import path
from .views.pages import company_list, company_detail, calculator

urlpatterns = [
    path("", company_list, name="company_list"),
    path("calculator/", calculator, name="calculator"),
    path("<str:corp_code>/", company_detail, name="company_detail"),
]

