"""
기업 재무 데이터 조회 뷰
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from apps.service.orchestrator import DataOrchestrator
from apps.models import CompanyFinancialObject
from apps.utils.utils import format_amount_korean, should_collect_company
import json


def company_list(request):
    """
    기업 목록 조회 페이지 (메인 페이지)
    GET /companies/
    """
    return render(request, 'companies/list.html')


def company_detail(request, corp_code):
    """
    기업 상세 정보 페이지
    GET /companies/{corp_code}/
    """
    return render(request, 'companies/detail.html', {'corp_code': corp_code})


def calculator(request):
    """
    재무 지표 계산기 페이지
    GET /companies/calculator/
    """
    return render(request, 'companies/calculator.html')


@api_view(['GET'])
def get_financial_data(request, corp_code):
    """
    기업 재무 데이터 조회 API
    GET /api/companies/{corp_code}/financial-data/
    
    DB에서 먼저 조회하고, 데이터가 없거나 오래되었으면 실시간 수집
    (4월 1일 기준으로 1년이 지났으면 재수집)
    """
    try:
        from django.apps import apps as django_apps
        CompanyModel = django_apps.get_model('apps', 'Company')
        YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
        
        # DB에서 먼저 조회 (prefetch_related로 쿼리 최적화)
        try:
            company = CompanyModel.objects.prefetch_related('yearly_data').get(corp_code=corp_code)
            yearly_data_list = list(company.yearly_data.all().order_by('year'))
            
            # DB에 데이터가 있고 최신이면 DB에서 반환
            # should_collect_company가 False면 수집 불필요 = DB 데이터가 최신 = DB에서 반환
            if yearly_data_list and not should_collect_company(corp_code):
                data = {
                    'corp_code': company.corp_code,
                    'company_name': company.company_name,
                    'business_type_code': company.business_type_code,
                    'business_type_name': company.business_type_name,
                    'bond_yield_5y': company.bond_yield_5y,
                    'passed_all_filters': company.passed_all_filters,
                    'filter_operating_income': company.filter_operating_income,
                    'filter_net_income': company.filter_net_income,
                    'filter_revenue_cagr': company.filter_revenue_cagr,
                    'filter_total_assets_operating_income_ratio': company.filter_total_assets_operating_income_ratio,
                    'yearly_data': [
                        {
                            'year': yd.year,
                            'revenue': yd.revenue,
                            'operating_income': yd.operating_income,
                            'net_income': yd.net_income,
                            'total_assets': yd.total_assets,
                            'total_equity': yd.total_equity,
                            'gross_profit_margin': yd.gross_profit_margin,
                            'selling_admin_expense_ratio': yd.selling_admin_expense_ratio,
                            'total_assets_operating_income_ratio': yd.total_assets_operating_income_ratio,
                            'roe': yd.roe,
                        }
                        for yd in yearly_data_list
                    ]
                }
                return Response(data, status=status.HTTP_200_OK)
        except CompanyModel.DoesNotExist:
            pass
        
        # DB에 없으면 실시간 수집
        orchestrator = DataOrchestrator()
        company_data = orchestrator.collect_company_data(corp_code)
        
        # CompanyFinancialObject를 딕셔너리로 변환
        data = {
            'corp_code': company_data.corp_code,
            'company_name': company_data.company_name,
            'business_type_code': company_data.business_type_code,
            'business_type_name': company_data.business_type_name,
            'bond_yield_5y': company_data.bond_yield_5y,
            'passed_all_filters': company_data.passed_all_filters,
            'filter_operating_income': company_data.filter_operating_income,
            'filter_net_income': company_data.filter_net_income,
            'filter_revenue_cagr': company_data.filter_revenue_cagr,
            'filter_total_assets_operating_income_ratio': company_data.filter_total_assets_operating_income_ratio,
            'yearly_data': [
                {
                    'year': yd.year,
                    'revenue': yd.revenue,
                    'operating_income': yd.operating_income,
                    'net_income': yd.net_income,
                    'total_assets': yd.total_assets,
                    'total_equity': yd.total_equity,
                    'gross_profit_margin': yd.gross_profit_margin,
                    'selling_admin_expense_ratio': yd.selling_admin_expense_ratio,
                    'total_assets_operating_income_ratio': yd.total_assets_operating_income_ratio,
                    'roe': yd.roe,
                }
                for yd in company_data.yearly_data
            ]
        }
        
        return Response(data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def batch_get_financial_data(request):
    """
    여러 기업의 재무 데이터를 한 번에 조회
    POST /api/companies/batch/
    
    Body: {
        "corp_codes": ["00126380", "00164742", ...]
    }
    """
    try:
        corp_codes = request.data.get('corp_codes', [])
        
        if not corp_codes:
            return Response(
                {'error': 'corp_codes 리스트가 필요합니다.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 중복 제거
        corp_codes = list(set(corp_codes))
        
        results = []
        errors = []
        
        # Django 모델 가져오기
        from django.apps import apps as django_apps
        CompanyModel = django_apps.get_model('apps', 'Company')
        
        orchestrator = DataOrchestrator()
        
        for corp_code_or_stock_code in corp_codes:
            try:
                # 종목코드인지 기업번호인지 확인 (종목코드는 6자리 숫자)
                if len(corp_code_or_stock_code) == 6 and corp_code_or_stock_code.isdigit():
                    # 종목코드를 기업번호로 변환
                    from apps.dart.client import DartClient
                    dart_client = DartClient()
                    corp_code = dart_client._get_corp_code_by_stock_code(corp_code_or_stock_code)
                    if not corp_code:
                        errors.append({
                            'corp_code': corp_code_or_stock_code,
                            'error': f'종목코드 {corp_code_or_stock_code}에 해당하는 기업번호를 찾을 수 없습니다.'
                        })
                        continue
                else:
                    corp_code = corp_code_or_stock_code
                
                # DB에서 먼저 조회
                try:
                    company = CompanyModel.objects.get(corp_code=corp_code)
                    # DB에 데이터가 있으면 DB에서 반환
                    results.append({
                        'corp_code': company.corp_code,
                        'company_name': company.company_name,
                        'business_type_name': company.business_type_name,
                        'passed_all_filters': company.passed_all_filters,
                    })
                    continue
                except CompanyModel.DoesNotExist:
                    # DB에 없으면 실시간 수집
                    pass
                
                # DB에 없으면 실시간 수집
                company_data = orchestrator.collect_company_data(corp_code)
                results.append({
                    'corp_code': company_data.corp_code,
                    'company_name': company_data.company_name,
                    'business_type_name': company_data.business_type_name,
                    'passed_all_filters': company_data.passed_all_filters,
                })
            except Exception as e:
                errors.append({
                    'corp_code': corp_code_or_stock_code,
                    'error': str(e)
                })
        
        return Response({
            'results': results,
            'errors': errors,
            'total': len(corp_codes),
            'success': len(results),
            'failed': len(errors)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_annual_report_link(request, corp_code):
    """
    사업보고서 링크 조회 API
    GET /api/companies/{corp_code}/annual-report-link/
    
    가장 최근 년도의 사업보고서 접수번호를 조회하여 DART 링크 생성
    """
    try:
        from apps.dart.client import DartClient
        from datetime import datetime
        
        client = DartClient()
        
        # 가장 최근 년도 계산 (사업보고서는 다음 해 3-4월에 제출되므로)
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        # 현재 월이 4월 이후면 작년 사업보고서가 이미 제출됨
        # 4월 이전이면 전년도 사업보고서를 찾아야 함
        if current_month >= 4:
            latest_year = current_year - 1
        else:
            latest_year = current_year - 2
        
        # 사업보고서 접수번호 조회
        rcept_no = client.get_annual_report_rcept_no(corp_code, str(latest_year))
        
        if rcept_no:
            dart_link = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
            return Response({
                'rcept_no': rcept_no,
                'year': latest_year,
                'link': dart_link
            }, status=status.HTTP_200_OK)
        else:
            # 최근 3년 동안 찾아보기
            for year_offset in range(1, 4):
                try_year = latest_year - year_offset
                rcept_no = client.get_annual_report_rcept_no(corp_code, str(try_year))
                if rcept_no:
                    dart_link = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
                    return Response({
                        'rcept_no': rcept_no,
                        'year': try_year,
                        'link': dart_link
                    }, status=status.HTTP_200_OK)
            
            return Response({
                'error': f'사업보고서를 찾을 수 없습니다.'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

