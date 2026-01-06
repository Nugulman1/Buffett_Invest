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
from apps.utils.utils import format_amount_korean, should_collect_company, load_company_from_db
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
    
    corp_code는 기업번호(8자리) 또는 종목코드(6자리)를 받을 수 있습니다.
    """
    # 종목코드인지 기업번호인지 확인 (종목코드는 6자리 숫자)
    if len(corp_code) == 6 and corp_code.isdigit():
        # 종목코드를 기업번호로 변환
        from apps.dart.client import DartClient
        dart_client = DartClient()
        converted_corp_code = dart_client._get_corp_code_by_stock_code(corp_code)
        if converted_corp_code:
            corp_code = converted_corp_code
    
    return render(request, 'companies/detail.html', {'corp_code': corp_code})


def calculator(request):
    """
    재무 지표 계산기 페이지
    GET /companies/calculator/
    """
    return render(request, 'companies/calculator.html')


def add_indicators(request, corp_code):
    """
    지표 추가 페이지
    GET /companies/<corp_code>/add-indicators/
    
    corp_code는 기업번호(8자리) 또는 종목코드(6자리)를 받을 수 있습니다.
    """
    # 종목코드인지 기업번호인지 확인 (종목코드는 6자리 숫자)
    if len(corp_code) == 6 and corp_code.isdigit():
        # 종목코드를 기업번호로 변환
        from apps.dart.client import DartClient
        dart_client = DartClient()
        converted_corp_code = dart_client._get_corp_code_by_stock_code(corp_code)
        if converted_corp_code:
            corp_code = converted_corp_code
    
    # 기업 정보 조회 (기업명 표시용)
    from django.apps import apps as django_apps
    CompanyModel = django_apps.get_model('apps', 'Company')
    company_name = ""
    try:
        company = CompanyModel.objects.get(corp_code=corp_code)
        company_name = company.company_name or ""
    except CompanyModel.DoesNotExist:
        pass
    
    return render(request, 'companies/add_indicators.html', {
        'corp_code': corp_code,
        'company_name': company_name
    })


@api_view(['GET'])
def get_financial_data(request, corp_code):
    """
    기업 재무 데이터 조회 API
    GET /api/companies/{corp_code}/financial-data/
    
    DB에서 먼저 조회하고, 데이터가 없거나 오래되었으면 실시간 수집
    (4월 1일 기준으로 1년이 지났으면 재수집)
    
    corp_code는 기업번호(8자리) 또는 종목코드(6자리)를 받을 수 있습니다.
    """
    try:
        from django.apps import apps as django_apps
        CompanyModel = django_apps.get_model('apps', 'Company')
        
        # 종목코드인지 기업번호인지 확인 (종목코드는 6자리 숫자)
        if len(corp_code) == 6 and corp_code.isdigit():
            # 종목코드를 기업번호로 변환
            from apps.dart.client import DartClient
            dart_client = DartClient()
            converted_corp_code = dart_client._get_corp_code_by_stock_code(corp_code)
            if not converted_corp_code:
                return Response(
                    {'error': f'종목코드 {corp_code}에 해당하는 기업번호를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            corp_code = converted_corp_code
        
        # DB에서 먼저 조회
        company_data = load_company_from_db(corp_code)
        if company_data and company_data.yearly_data and not should_collect_company(corp_code):
            # memo는 별도로 조회
            try:
                company = CompanyModel.objects.get(corp_code=corp_code)
                memo = company.memo
            except CompanyModel.DoesNotExist:
                memo = None
            
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
                'memo': memo,
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
                        'fcf': yd.fcf,
                        'roic': yd.roic,
                        'wacc': yd.wacc,
                    }
                    for yd in company_data.yearly_data
                ]
            }
            return Response(data, status=status.HTTP_200_OK)
        
        # DB에 없으면 실시간 수집
        orchestrator = DataOrchestrator()
        company_data = orchestrator.collect_company_data(corp_code)
        
        # 수집 후 DB에서 다시 조회 (새로 추가된 필드 포함)
        company_data_from_db = load_company_from_db(corp_code)
        if company_data_from_db:
            # memo는 별도로 조회
            try:
                company = CompanyModel.objects.get(corp_code=corp_code)
                memo = company.memo
            except CompanyModel.DoesNotExist:
                memo = None
            
            # CompanyFinancialObject를 딕셔너리로 변환
            data = {
                'corp_code': company_data_from_db.corp_code,
                'company_name': company_data_from_db.company_name,
                'business_type_code': company_data_from_db.business_type_code,
                'business_type_name': company_data_from_db.business_type_name,
                'bond_yield_5y': company_data_from_db.bond_yield_5y,
                'passed_all_filters': company_data_from_db.passed_all_filters,
                'filter_operating_income': company_data_from_db.filter_operating_income,
                'filter_net_income': company_data_from_db.filter_net_income,
                'filter_revenue_cagr': company_data_from_db.filter_revenue_cagr,
                'filter_total_assets_operating_income_ratio': company_data_from_db.filter_total_assets_operating_income_ratio,
                'memo': memo,
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
                        'fcf': yd.fcf,
                        'roic': yd.roic,
                        'wacc': yd.wacc,
                    }
                    for yd in company_data_from_db.yearly_data
                ]
            }
        else:
            # 수집 실패 시 빈 데이터 반환
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
                'memo': None,
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
                        'fcf': None,
                        'roic': None,
                        'wacc': None,
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


@api_view(['GET'])
def get_calculator_data(request, corp_code):
    """
    계산기용 데이터 조회 API
    GET /api/companies/{corp_code}/calculator-data/?year=2023
    
    특정 년도의 자기자본, 영업이익, 국채수익률을 반환합니다.
    
    corp_code는 기업번호(8자리) 또는 종목코드(6자리)를 받을 수 있습니다.
    """
    try:
        from django.apps import apps as django_apps
        CompanyModel = django_apps.get_model('apps', 'Company')
        YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
        
        # 년도 파라미터 확인
        year = request.query_params.get('year')
        if not year:
            return Response(
                {'error': 'year 파라미터가 필요합니다.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            year = int(year)
        except ValueError:
            return Response(
                {'error': 'year는 정수여야 합니다.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 종목코드인지 기업번호인지 확인 (종목코드는 6자리 숫자)
        if len(corp_code) == 6 and corp_code.isdigit():
            # 종목코드를 기업번호로 변환
            from apps.dart.client import DartClient
            dart_client = DartClient()
            converted_corp_code = dart_client._get_corp_code_by_stock_code(corp_code)
            if not converted_corp_code:
                return Response(
                    {'error': f'종목코드 {corp_code}에 해당하는 기업번호를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            corp_code = converted_corp_code
        
        # Company 모델 조회 (국채수익률)
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
            bond_yield_5y = company.bond_yield_5y or 0.0
        except CompanyModel.DoesNotExist:
            return Response(
                {'error': f'기업코드 {corp_code}에 해당하는 데이터를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # YearlyFinancialData 모델 조회 (해당 년도)
        try:
            yearly_data = YearlyFinancialDataModel.objects.get(company=company, year=year)
            total_equity = yearly_data.total_equity or 0
            operating_income = yearly_data.operating_income or 0
        except YearlyFinancialDataModel.DoesNotExist:
            return Response(
                {'error': f'{year}년 데이터를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 응답 데이터 반환
        return Response({
            'corp_code': corp_code,
            'year': year,
            'total_equity': total_equity,
            'operating_income': operating_income,
            'bond_yield_5y': bond_yield_5y
        }, status=status.HTTP_200_OK)
        
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


@api_view(['POST'])
def save_memo(request, corp_code):
    """
    기업 메모 저장 API
    POST /api/companies/{corp_code}/memo/
    
    Body: {"memo": "메모 내용"}
    
    corp_code는 기업번호(8자리) 또는 종목코드(6자리)를 받을 수 있습니다.
    """
    try:
        from django.apps import apps as django_apps
        CompanyModel = django_apps.get_model('apps', 'Company')
        
        # 종목코드인지 기업번호인지 확인 (종목코드는 6자리 숫자)
        if len(corp_code) == 6 and corp_code.isdigit():
            # 종목코드를 기업번호로 변환
            from apps.dart.client import DartClient
            dart_client = DartClient()
            converted_corp_code = dart_client._get_corp_code_by_stock_code(corp_code)
            if not converted_corp_code:
                return Response(
                    {'error': f'종목코드 {corp_code}에 해당하는 기업번호를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            corp_code = converted_corp_code
        
        memo = request.data.get('memo', '')
        
        # Company 모델 업데이트 또는 생성
        company, created = CompanyModel.objects.update_or_create(
            corp_code=corp_code,
            defaults={'memo': memo}
        )
        
        return Response({
            'corp_code': company.corp_code,
            'memo': company.memo,
            'created': created
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def save_calculated_indicators(request, corp_code):
    """
    계산 지표 저장 API
    POST /api/companies/{corp_code}/calculated-indicators/
    
    Body: {
        "year": 2023,
        "cfo": 1000000000,
        "tangible_asset_acquisition": 500000000,
        "intangible_asset_acquisition": 100000000,
        "operating_income": 800000000,
        "tax_rate": 25.0,
        "equity": 5000000000,
        "short_term_borrowings": 1000000000,
        "current_portion_of_long_term_borrowings": 200000000,
        "long_term_borrowings": 2000000000,
        "bonds": 500000000,
        "lease_liabilities": 300000000,
        "cash_and_cash_equivalents": 1000000000,
        "interest_expense": 200000000,
        "bond_yield": 3.5,
        "equity_risk_premium": 5.0
    }
    
    corp_code는 기업번호(8자리) 또는 종목코드(6자리)를 받을 수 있습니다.
    """
    try:
        from django.apps import apps as django_apps
        from apps.service.calculator import IndicatorCalculator
        from apps.models import YearlyFinancialDataObject
        
        CompanyModel = django_apps.get_model('apps', 'Company')
        YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
        
        # 종목코드인지 기업번호인지 확인 (종목코드는 6자리 숫자)
        if len(corp_code) == 6 and corp_code.isdigit():
            # 종목코드를 기업번호로 변환
            from apps.dart.client import DartClient
            dart_client = DartClient()
            converted_corp_code = dart_client._get_corp_code_by_stock_code(corp_code)
            if not converted_corp_code:
                return Response(
                    {'error': f'종목코드 {corp_code}에 해당하는 기업번호를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            corp_code = converted_corp_code
        
        # Company 확인
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
        except CompanyModel.DoesNotExist:
            return Response(
                {'error': f'기업을 찾을 수 없습니다. (corp_code: {corp_code})'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # YearlyFinancialData 확인
        year = request.data.get('year')
        if not year:
            return Response(
                {'error': 'year 필드가 필요합니다.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            yearly_data_db = YearlyFinancialDataModel.objects.get(company=company, year=year)
        except YearlyFinancialDataModel.DoesNotExist:
            return Response(
                {'error': f'{year}년도 데이터를 찾을 수 없습니다. 먼저 재무 데이터를 수집해주세요.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 입력 데이터로 YearlyFinancialDataObject 생성
        yearly_data_obj = YearlyFinancialDataObject(year=year, corp_code=corp_code)
        yearly_data_obj.cfo = request.data.get('cfo', 0) or 0
        yearly_data_obj.tangible_asset_acquisition = request.data.get('tangible_asset_acquisition', 0) or 0
        yearly_data_obj.intangible_asset_acquisition = request.data.get('intangible_asset_acquisition', 0) or 0
        yearly_data_obj.operating_income = request.data.get('operating_income', 0) or 0
        yearly_data_obj.equity = request.data.get('equity', 0) or 0
        yearly_data_obj.short_term_borrowings = request.data.get('short_term_borrowings', 0) or 0
        yearly_data_obj.current_portion_of_long_term_borrowings = request.data.get('current_portion_of_long_term_borrowings', 0) or 0
        yearly_data_obj.long_term_borrowings = request.data.get('long_term_borrowings', 0) or 0
        yearly_data_obj.bonds = request.data.get('bonds', 0) or 0
        yearly_data_obj.lease_liabilities = request.data.get('lease_liabilities', 0) or 0
        yearly_data_obj.convertible_bonds = request.data.get('convertible_bonds', 0) or 0
        yearly_data_obj.cash_and_cash_equivalents = request.data.get('cash_and_cash_equivalents', 0) or 0
        yearly_data_obj.interest_expense = request.data.get('interest_expense', 0) or 0
        
        # 계산 수행 (문자열을 숫자로 변환)
        tax_rate = float(request.data.get('tax_rate', 25.0)) / 100.0
        bond_yield = float(request.data.get('bond_yield', 3.5))
        equity_risk_premium = float(request.data.get('equity_risk_premium', 5.0))
        
        fcf = IndicatorCalculator.calculate_fcf(yearly_data_obj)
        roic = IndicatorCalculator.calculate_roic(yearly_data_obj, tax_rate)
        wacc = IndicatorCalculator.calculate_wacc(yearly_data_obj, bond_yield, tax_rate, equity_risk_premium)
        
        # DB 업데이트
        yearly_data_db.fcf = fcf
        yearly_data_db.roic = roic
        yearly_data_db.wacc = wacc
        yearly_data_db.save()
        
        return Response({
            'corp_code': corp_code,
            'year': year,
            'fcf': fcf,
            'roic': roic,
            'wacc': wacc
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def save_manual_financial_data(request, corp_code):
    """
    수기 재무 데이터 저장 API
    POST /api/companies/{corp_code}/manual-financial-data/
    
    Body: {
        "year": 2023,
        "revenue": 1000000000,
        "operating_income": 500000000,
        "net_income": 400000000,
        "total_assets": 5000000000,
        "total_equity": 3000000000
    }
    
    corp_code는 기업번호(8자리) 또는 종목코드(6자리)를 받을 수 있습니다.
    """
    try:
        from django.apps import apps as django_apps
        from apps.service.calculator import IndicatorCalculator
        from apps.service.filter import CompanyFilter
        from apps.models import YearlyFinancialDataObject
        from apps.utils.utils import load_company_from_db
        from django.utils import timezone
        from django.db import transaction
        
        CompanyModel = django_apps.get_model('apps', 'Company')
        YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
        
        # 종목코드인지 기업번호인지 확인 (종목코드는 6자리 숫자)
        if len(corp_code) == 6 and corp_code.isdigit():
            # 종목코드를 기업번호로 변환
            from apps.dart.client import DartClient
            dart_client = DartClient()
            converted_corp_code = dart_client._get_corp_code_by_stock_code(corp_code)
            if not converted_corp_code:
                return Response(
                    {'error': f'종목코드 {corp_code}에 해당하는 기업번호를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            corp_code = converted_corp_code
        
        # 입력 데이터 검증 및 타입 변환
        year = request.data.get('year')
        try:
            year = int(year) if year else None
        except (ValueError, TypeError):
            year = None
        
        if not year:
            return Response(
                {'error': 'year 필드가 필요합니다.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 숫자 필드들을 정수로 변환 (문자열도 처리)
        def to_int(value, default=0):
            try:
                if value is None or value == '':
                    return default
                return int(float(value))  # 문자열 숫자도 처리
            except (ValueError, TypeError):
                return default
        
        revenue = to_int(request.data.get('revenue'), 0)
        operating_income = to_int(request.data.get('operating_income'), 0)
        net_income = to_int(request.data.get('net_income'), 0)
        total_assets = to_int(request.data.get('total_assets'), 0)
        total_equity = to_int(request.data.get('total_equity'), 0)
        
        # SQLite 잠금 문제 해결을 위한 재시도 로직
        max_retries = 3
        retry_delay = 0.1  # 100ms
        
        for attempt in range(max_retries):
            try:
                with transaction.atomic():
                    # Company 모델 확인 또는 생성
                    company, created = CompanyModel.objects.get_or_create(
                        corp_code=corp_code,
                        defaults={
                            'company_name': '',
                            'business_type_code': '',
                            'business_type_name': '',
                        }
                    )
                    
                    # YearlyFinancialDataObject 생성 (계산용)
                    yearly_data_obj = YearlyFinancialDataObject(year=year, corp_code=corp_code)
                    yearly_data_obj.revenue = revenue
                    yearly_data_obj.operating_income = operating_income
                    yearly_data_obj.net_income = net_income
                    yearly_data_obj.total_assets = total_assets
                    yearly_data_obj.total_equity = total_equity
                    
                    # 총자산영업이익률 계산
                    total_assets_operating_income_ratio = IndicatorCalculator.calculate_total_assets_operating_income_ratio(yearly_data_obj)
                    
                    # ROE 계산
                    roe = IndicatorCalculator.calculate_roe(yearly_data_obj)
                    
                    # YearlyFinancialData 모델 저장 또는 업데이트
                    yearly_data_db, created = YearlyFinancialDataModel.objects.update_or_create(
                        company=company,
                        year=year,
                        defaults={
                            'revenue': revenue,
                            'operating_income': operating_income,
                            'net_income': net_income,
                            'total_assets': total_assets,
                            'total_equity': total_equity,
                            'total_assets_operating_income_ratio': total_assets_operating_income_ratio,
                            'roe': roe,
                        }
                    )
                
                # 트랜잭션 성공 시 루프 종료
                break
                
            except Exception as e:
                error_message = str(e)
                is_db_locked = 'database is locked' in error_message.lower()
                
                if is_db_locked and attempt < max_retries - 1:
                    # SQLite 잠금 오류인 경우 재시도
                    import time
                    time.sleep(retry_delay * (attempt + 1))  # 지수 백오프
                    continue
                else:
                    # 다른 오류이거나 재시도 횟수 초과
                    raise
        
        # 트랜잭션 완료 후 연결 명시적으로 닫기 (SQLite 잠금 방지)
        from django.db import connection
        connection.close()
        
        # DB에서 CompanyFinancialObject 로드 (재시도 로직 포함)
        company_data = None
        for attempt in range(max_retries):
            try:
                company_data = load_company_from_db(corp_code)
                # 성공 시 루프 종료
                break
            except Exception as e:
                error_message = str(e)
                is_db_locked = 'database is locked' in error_message.lower()
                
                if is_db_locked and attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    return Response(
                        {'error': f'데이터 로드 중 오류 발생: {error_message}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
        
        # load_company_from_db 성공 후 연결 닫기
        from django.db import connection
        connection.close()
        
        if not company_data:
            return Response(
                {'error': '데이터를 로드할 수 없습니다.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # 필터 재검사
        try:
            CompanyFilter.apply_all_filters(company_data)
        except Exception as e:
            return Response(
                {'error': f'필터 적용 중 오류 발생: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # 필터 결과를 Company 모델에 저장
        try:
            with transaction.atomic():
                CompanyModel.objects.filter(corp_code=corp_code).update(
                    passed_all_filters=company_data.passed_all_filters,
                    filter_operating_income=company_data.filter_operating_income,
                    filter_net_income=company_data.filter_net_income,
                    filter_revenue_cagr=company_data.filter_revenue_cagr,
                    filter_total_assets_operating_income_ratio=company_data.filter_total_assets_operating_income_ratio,
                )
        except Exception as e:
            return Response(
                {'error': f'필터 결과 저장 중 오류 발생: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        return Response({
            'corp_code': corp_code,
            'year': year,
            'revenue': revenue,
            'operating_income': operating_income,
            'net_income': net_income,
            'total_assets': total_assets,
            'total_equity': total_equity,
            'total_assets_operating_income_ratio': total_assets_operating_income_ratio,
            'roe': roe,
            'passed_all_filters': company_data.passed_all_filters,
            'filter_operating_income': company_data.filter_operating_income,
            'filter_net_income': company_data.filter_net_income,
            'filter_revenue_cagr': company_data.filter_revenue_cagr,
            'filter_total_assets_operating_income_ratio': company_data.filter_total_assets_operating_income_ratio,
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': f'서버 오류가 발생했습니다: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_annual_report_link(request, corp_code):
    """
    사업보고서 링크 조회 API
    GET /api/companies/{corp_code}/annual-report-link/
    
    가장 최근 년도의 사업보고서 접수번호를 조회하여 DART 링크 생성
    
    corp_code는 기업번호(8자리) 또는 종목코드(6자리)를 받을 수 있습니다.
    """
    try:
        from apps.dart.client import DartClient
        from datetime import datetime
        
        # 종목코드인지 기업번호인지 확인 (종목코드는 6자리 숫자)
        if len(corp_code) == 6 and corp_code.isdigit():
            # 종목코드를 기업번호로 변환
            dart_client = DartClient()
            converted_corp_code = dart_client._get_corp_code_by_stock_code(corp_code)
            if not converted_corp_code:
                return Response(
                    {'error': f'종목코드 {corp_code}에 해당하는 기업번호를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            corp_code = converted_corp_code
        
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

