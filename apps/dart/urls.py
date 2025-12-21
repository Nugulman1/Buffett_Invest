"""
DART URL 라우팅
"""
from django.urls import path
from . import views

urlpatterns = [
    path('company/<str:corp_code>/', views.company_info, name='company_info'),
]

