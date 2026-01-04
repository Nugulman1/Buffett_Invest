"""
기업 재무 데이터 URL 라우팅
"""
from django.urls import path
from . import views

urlpatterns = [
    # 프론트엔드 페이지
    path('', views.company_list, name='company_list'),
    path('calculator/', views.calculator, name='calculator'),
    path('<str:corp_code>/', views.company_detail, name='company_detail'),
]

