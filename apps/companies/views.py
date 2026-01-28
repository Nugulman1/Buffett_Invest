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
from apps.utils.utils import format_amount_korean, should_collect_company, load_company_from_db, load_passed_companies_json, get_bond_yield_5y
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
    
    corp_code는 종목코드(6자리) 또는 기업번호(8자리)를 받을 수 있습니다.
    - 종목코드(6자리): 기업명 검색 결과에서 선택한 경우 또는 직접 입력
    - 기업번호(8자리): 기업명 검색 결과에서 선택한 경우 (corp_code로 전달)
    """
    # 종목코드인지 기업번호인지 확인 (종목코드는 6자리 숫자)
    if len(corp_code) == 6 and corp_code.isdigit():
        # 종목코드를 기업번호로 변환
        from apps.dart.client import DartClient
        dart_client = DartClient()
        converted_corp_code = dart_client._get_corp_code_by_stock_code(corp_code)
        if converted_corp_code:
            corp_code = converted_corp_code
        else:
            # 종목코드 변환 실패
            from django.http import HttpResponseNotFound
            return HttpResponseNotFound('종목코드를 찾을 수 없습니다.')
    # 기업번호(8자리)인 경우 그대로 사용
    
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
    
    corp_code는 종목코드(6자리) 또는 기업번호(8자리)를 받을 수 있습니다.
    - 종목코드(6자리): 기업명 검색 결과에서 선택한 경우 또는 직접 입력
    - 기업번호(8자리): 기업명 검색 결과에서 선택한 경우 (corp_code로 전달)
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
def get_passed_companies(request):
    """
    필터 통과 기업 목록 조회 API
    GET /api/companies/passed/?page=1&page_size=10
    
    JSON 파일에서 필터 통과 기업 목록을 읽어서 페이지네이션과 함께 반환합니다.
    """
    from django.conf import settings
    import math
    
    # 페이지네이션 파라미터
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 10))
    
    # 유효성 검사
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10
    
    # JSON 파일 경로
    json_file = settings.BASE_DIR / 'passed_filters_companies.json'
    
    # JSON 파일 읽기
    data = load_passed_companies_json(json_file)
    
    # 전체 목록 포맷팅
    all_companies = []
    for company in data.get('companies', []):
        all_companies.append({
            'stock_code': company.get('stock_code', ''),
            'company_name': company.get('company_name', ''),
            'corp_code': company.get('corp_code', '')
        })
    
    total = len(all_companies)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    
    # 페이지 범위 검증
    if page > total_pages and total_pages > 0:
        page = total_pages
    
    # 페이지별 슬라이싱
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    companies = all_companies[start_idx:end_idx]
    
    return Response({
        'companies': companies,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'last_updated': data.get('last_updated')
    })


@api_view(['GET'])
def search_companies(request):
    """
    기업명 검색 API
    GET /api/companies/search/?q=검색어&limit=10
    
    DB에 저장된 기업 목록에서 기업명으로 검색합니다.
    """
    from django.apps import apps as django_apps
    CompanyModel = django_apps.get_model('apps', 'Company')
    
    # 검색어 가져오기
    search_query = request.GET.get('q', '').strip()
    limit = int(request.GET.get('limit', 10))
    
    # 빈 검색어 처리
    if not search_query:
        return Response({
            'companies': [],
            'total': 0
        })
    
    # DB에서 검색 (부분 일치, 대소문자 구분 없음)
    companies = CompanyModel.objects.filter(
        company_name__icontains=search_query
    )[:limit]
    
    # 결과 포맷팅
    results = []
    for company in companies:
        results.append({
            'corp_code': company.corp_code,
            'company_name': company.company_name or '',
        })
    
    return Response({
        'companies': results,
        'total': len(results)
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
            # memo와 memo_updated_at은 별도로 조회
            try:
                company = CompanyModel.objects.get(corp_code=corp_code)
                memo = company.memo
                memo_updated_at = company.memo_updated_at.isoformat() if company.memo_updated_at else None
            except CompanyModel.DoesNotExist:
                memo = None
                memo_updated_at = None
            
            # CompanyFinancialObject를 딕셔너리로 변환
            data = {
                'corp_code': company_data.corp_code,
                'company_name': company_data.company_name,
                'bond_yield_5y': get_bond_yield_5y() * 100,  # 백분율로 변환
                'passed_all_filters': company_data.passed_all_filters,
                'filter_operating_income': company_data.filter_operating_income,
                'filter_net_income': company_data.filter_net_income,
                'filter_revenue_cagr': company_data.filter_revenue_cagr,
                'filter_operating_margin': company_data.filter_operating_margin,
                'filter_roe': company_data.filter_roe,
                'memo': memo,
                'memo_updated_at': memo_updated_at,
                'yearly_data': [
                    {
                        'year': yd.year,
                        'revenue': yd.revenue,
                        'operating_income': yd.operating_income,
                        'net_income': yd.net_income,
                        'total_assets': yd.total_assets,
                        'total_equity': yd.total_equity,
                        'operating_margin': yd.operating_margin,
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
            # 필터 통과 시 JSON 파일에 추가
            if company_data_from_db.passed_all_filters:
                from apps.utils.utils import get_stock_code_by_corp_code, save_passed_companies_json
                
                stock_code = get_stock_code_by_corp_code(corp_code)
                if stock_code:
                    company_name = company_data_from_db.company_name or ''
                    # JSON 파일에 저장
                    save_passed_companies_json(stock_code, company_name, corp_code)
            
            # memo와 memo_updated_at은 별도로 조회
            try:
                company = CompanyModel.objects.get(corp_code=corp_code)
                memo = company.memo
                memo_updated_at = company.memo_updated_at.isoformat() if company.memo_updated_at else None
            except CompanyModel.DoesNotExist:
                memo = None
                memo_updated_at = None
            
            # CompanyFinancialObject를 딕셔너리로 변환
            data = {
                'corp_code': company_data_from_db.corp_code,
                'company_name': company_data_from_db.company_name,
                'bond_yield_5y': get_bond_yield_5y() * 100,  # 백분율로 변환
                'passed_all_filters': company_data_from_db.passed_all_filters,
                'filter_operating_income': company_data_from_db.filter_operating_income,
                'filter_net_income': company_data_from_db.filter_net_income,
                'filter_revenue_cagr': company_data_from_db.filter_revenue_cagr,
                'filter_operating_margin': company_data_from_db.filter_operating_margin,
                'filter_roe': company_data_from_db.filter_roe,
                'memo': memo,
                'memo_updated_at': memo_updated_at,
                'yearly_data': [
                    {
                        'year': yd.year,
                        'revenue': yd.revenue,
                        'operating_income': yd.operating_income,
                        'net_income': yd.net_income,
                        'total_assets': yd.total_assets,
                        'total_equity': yd.total_equity,
                        'operating_margin': yd.operating_margin,
                        'roe': yd.roe,
                        'fcf': yd.fcf,
                        'roic': yd.roic,
                        'wacc': yd.wacc,
                    }
                    for yd in company_data_from_db.yearly_data
                ]
            }
        else:
            # 수집 실패 시 빈 데이터 반환 (메모는 DB에서 조회)
            try:
                company = CompanyModel.objects.get(corp_code=corp_code)
                memo = company.memo
                memo_updated_at = company.memo_updated_at.isoformat() if company.memo_updated_at else None
            except CompanyModel.DoesNotExist:
                memo = None
                memo_updated_at = None
            
            data = {
                'corp_code': company_data.corp_code,
                'company_name': company_data.company_name,
                'bond_yield_5y': get_bond_yield_5y() * 100,  # 백분율로 변환
                'passed_all_filters': company_data.passed_all_filters,
                'filter_operating_income': company_data.filter_operating_income,
                'filter_net_income': company_data.filter_net_income,
                'filter_revenue_cagr': company_data.filter_revenue_cagr,
                'filter_operating_margin': company_data.filter_operating_margin,
                'filter_roe': company_data.filter_roe,
                'memo': memo,
                'memo_updated_at': memo_updated_at,
                'yearly_data': [
                    {
                        'year': yd.year,
                        'revenue': yd.revenue,
                        'operating_income': yd.operating_income,
                        'net_income': yd.net_income,
                        'total_assets': yd.total_assets,
                        'total_equity': yd.total_equity,
                        'operating_margin': yd.operating_margin,
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
        
        # Company 모델 조회
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
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
            'bond_yield_5y': get_bond_yield_5y() * 100  # 백분율로 변환
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
        
        from django.utils import timezone
        
        memo = request.data.get('memo', '')
        
        # 메모 저장 시 현재 시간 기록
        now = timezone.now()
        
        # Company 모델 업데이트 또는 생성
        company, created = CompanyModel.objects.update_or_create(
            corp_code=corp_code,
            defaults={
                'memo': memo,
                'memo_updated_at': now if memo else None  # 메모가 있으면 날짜 기록, 없으면 None
            }
        )
        
        return Response({
            'corp_code': company.corp_code,
            'memo': company.memo,
            'memo_updated_at': company.memo_updated_at.isoformat() if company.memo_updated_at else None,
            'created': created
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def _process_single_year_indicators(year_data, corp_code, company):
    """
    단일 년도 지표 계산 및 저장
    
    Args:
        year_data: 년도별 재무 데이터 딕셔너리
        corp_code: 기업번호
        company: Company 모델 인스턴스
    
    Returns:
        dict: 계산 결과 (corp_code, year, fcf, roic, wacc)
    
    Raises:
        ValueError: 필수 필드 누락
        YearlyFinancialDataModel.DoesNotExist: 년도 데이터 없음
        Exception: 기타 오류
    """
    from django.apps import apps as django_apps
    from apps.service.calculator import IndicatorCalculator
    from apps.models import YearlyFinancialDataObject
    
    YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
    
    # YearlyFinancialData 확인
    year = year_data.get('year')
    if not year:
        raise ValueError('year 필드가 필요합니다.')
    
    try:
        yearly_data_db = YearlyFinancialDataModel.objects.get(company=company, year=year)
    except YearlyFinancialDataModel.DoesNotExist:
        raise YearlyFinancialDataModel.DoesNotExist(f'{year}년도 데이터를 찾을 수 없습니다. 먼저 재무 데이터를 수집해주세요.')
    
    # 입력 데이터로 YearlyFinancialDataObject 생성
    yearly_data_obj = YearlyFinancialDataObject(year=year)
    yearly_data_obj.cfo = year_data.get('cfo', 0) or 0
    yearly_data_obj.tangible_asset_acquisition = year_data.get('tangible_asset_acquisition', 0) or 0
    yearly_data_obj.intangible_asset_acquisition = year_data.get('intangible_asset_acquisition', 0) or 0
    yearly_data_obj.operating_income = year_data.get('operating_income', 0) or 0
    yearly_data_obj.equity = year_data.get('equity', 0) or 0
    # 이자부채 통합: 프론트엔드에서 6개 필드로 보내면 합산, 단일 필드로 보내면 그대로 사용
    interest_bearing_debt = (
        (year_data.get('short_term_borrowings', 0) or 0) +
        (year_data.get('current_portion_of_long_term_borrowings', 0) or 0) +
        (year_data.get('long_term_borrowings', 0) or 0) +
        (year_data.get('bonds', 0) or 0) +
        (year_data.get('lease_liabilities', 0) or 0) +
        (year_data.get('convertible_bonds', 0) or 0)
    )
    # interest_bearing_debt 필드가 직접 전달되면 우선 사용
    if 'interest_bearing_debt' in year_data and year_data.get('interest_bearing_debt'):
        yearly_data_obj.interest_bearing_debt = year_data.get('interest_bearing_debt', 0) or 0
    else:
        yearly_data_obj.interest_bearing_debt = interest_bearing_debt
    yearly_data_obj.cash_and_cash_equivalents = year_data.get('cash_and_cash_equivalents', 0) or 0
    yearly_data_obj.interest_expense = year_data.get('interest_expense', 0) or 0
    
    # 계산 수행 (문자열을 숫자로 변환)
    tax_rate = float(year_data.get('tax_rate', 25.0)) / 100.0
    bond_yield = float(year_data.get('bond_yield', 3.5))
    equity_risk_premium = float(year_data.get('equity_risk_premium', 5.0))
    
    fcf = IndicatorCalculator.calculate_fcf(yearly_data_obj)
    roic = IndicatorCalculator.calculate_roic(yearly_data_obj, tax_rate)
    wacc = IndicatorCalculator.calculate_wacc(yearly_data_obj, bond_yield, tax_rate, equity_risk_premium)
    
    # DB 업데이트
    yearly_data_db.fcf = fcf
    yearly_data_db.roic = roic
    yearly_data_db.wacc = wacc
    yearly_data_db.save()
    
    return {
        'corp_code': corp_code,
        'year': year,
        'fcf': fcf,
        'roic': roic,
        'wacc': wacc
    }


@api_view(['POST'])
def save_calculated_indicators(request, corp_code):
    """
    계산 지표 저장 API
    POST /api/companies/{corp_code}/calculated-indicators/
    
    Body: 단일 객체 또는 배열
    {
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
    
    또는
    
    [
        { "year": 2023, ... },
        { "year": 2024, ... }
    ]
    
    corp_code는 기업번호(8자리) 또는 종목코드(6자리)를 받을 수 있습니다.
    """
    try:
        from django.apps import apps as django_apps
        
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
        
        # 항상 배열로 정규화
        data_list = request.data if isinstance(request.data, list) else [request.data]
        
        # 각 년도별 처리
        results = []
        errors = []
        
        for idx, year_data in enumerate(data_list):
            try:
                result = _process_single_year_indicators(year_data, corp_code, company)
                results.append(result)
            except YearlyFinancialDataModel.DoesNotExist as e:
                errors.append({
                    'index': idx,
                    'year': year_data.get('year'),
                    'error': str(e)
                })
            except ValueError as e:
                errors.append({
                    'index': idx,
                    'year': year_data.get('year'),
                    'error': str(e)
                })
            except Exception as e:
                errors.append({
                    'index': idx,
                    'year': year_data.get('year'),
                    'error': str(e)
                })
        
        # 응답 생성
        response_data = {
            'results': results,
            'success_count': len(results),
            'total_count': len(data_list)
        }
        
        if errors:
            response_data['errors'] = errors
        
        # 모든 년도가 실패한 경우
        if not results:
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)
        
        return Response(response_data, status=status.HTTP_200_OK)
        
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
                        }
                    )
                    
                    # YearlyFinancialDataObject 생성 (계산용)
                    yearly_data_obj = YearlyFinancialDataObject(year=year)
                    yearly_data_obj.revenue = revenue
                    yearly_data_obj.operating_income = operating_income
                    yearly_data_obj.net_income = net_income
                    yearly_data_obj.total_assets = total_assets
                    yearly_data_obj.total_equity = total_equity
                    
                    # 영업이익률 계산
                    operating_margin = IndicatorCalculator.calculate_operating_margin(yearly_data_obj)
                    
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
                            'operating_margin': operating_margin,
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
                    filter_operating_margin=company_data.filter_operating_margin,
                    filter_roe=company_data.filter_roe,
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
            'operating_margin': operating_margin,
            'roe': roe,
            'passed_all_filters': company_data.passed_all_filters,
            'filter_operating_income': company_data.filter_operating_income,
            'filter_net_income': company_data.filter_net_income,
            'filter_revenue_cagr': company_data.filter_revenue_cagr,
            'filter_operating_margin': company_data.filter_operating_margin,
            'filter_roe': company_data.filter_roe,
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


@api_view(['GET'])
def get_favorites(request):
    """
    즐겨찾기 목록 조회 API
    GET /api/companies/favorites/
    
    그룹별로 그룹화된 즐겨찾기 목록을 반환합니다.
    """
    try:
        from django.apps import apps as django_apps
        FavoriteGroupModel = django_apps.get_model('apps', 'FavoriteGroup')
        FavoriteModel = django_apps.get_model('apps', 'Favorite')
        
        # 모든 그룹 조회
        groups = FavoriteGroupModel.objects.all().order_by('name')
        
        # 그룹별로 즐겨찾기 목록 구성 (빈 그룹도 포함)
        result = []
        for group in groups:
            favorites = FavoriteModel.objects.filter(group=group).select_related('company').order_by('company__company_name')
            result.append({
                'group_id': group.id,
                'group_name': group.name,
                'favorites': [
                    {
                        'id': fav.id,
                        'corp_code': fav.company.corp_code,
                        'company_name': fav.company.company_name or '',
                        'created_at': fav.created_at.isoformat() if fav.created_at else None
                    }
                    for fav in favorites
                ]
            })
        
        return Response({
            'groups': result
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST', 'DELETE'])
def favorite(request, corp_code):
    """
    즐겨찾기 추가 및 삭제 API
    POST /api/companies/<corp_code>/favorites/ - 즐겨찾기 추가
    DELETE /api/companies/<corp_code>/favorites/ - 즐겨찾기 삭제
    
    corp_code는 기업번호(8자리) 또는 종목코드(6자리)를 받을 수 있습니다.
    """
    try:
        from django.apps import apps as django_apps
        CompanyModel = django_apps.get_model('apps', 'Company')
        FavoriteGroupModel = django_apps.get_model('apps', 'FavoriteGroup')
        FavoriteModel = django_apps.get_model('apps', 'Favorite')
        
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
        
        # 기업 확인
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
        except CompanyModel.DoesNotExist:
            return Response(
                {'error': f'기업코드 {corp_code}에 해당하는 기업을 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if request.method == 'POST':
            # 그룹 ID 확인
            group_id = request.data.get('group_id')
            if not group_id:
                return Response(
                    {'error': 'group_id가 필요합니다.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                group_id = int(group_id)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'group_id는 정수여야 합니다.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 그룹 확인
            try:
                group = FavoriteGroupModel.objects.get(id=group_id)
            except FavoriteGroupModel.DoesNotExist:
                return Response(
                    {'error': f'그룹 ID {group_id}를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            # 즐겨찾기 추가 (이미 있으면 에러)
            favorite, created = FavoriteModel.objects.get_or_create(
                group=group,
                company=company,
                defaults={}
            )
            
            if not created:
                return Response(
                    {'error': '이미 즐겨찾기에 추가된 기업입니다.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            return Response({
                'id': favorite.id,
                'corp_code': company.corp_code,
                'company_name': company.company_name or '',
                'group_id': group.id,
                'group_name': group.name,
                'created_at': favorite.created_at.isoformat() if favorite.created_at else None
            }, status=status.HTTP_201_CREATED)
        elif request.method == 'DELETE':
            # 즐겨찾기 삭제 (모든 그룹에서)
            deleted_count, _ = FavoriteModel.objects.filter(company=company).delete()
            
            if deleted_count == 0:
                return Response(
                    {'error': '즐겨찾기에 없는 기업입니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            return Response({
                'corp_code': corp_code,
                'deleted_count': deleted_count
            }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
def favorite_detail(request, favorite_id):
    """
    즐겨찾기 삭제 API (특정 그룹에서만)
    DELETE /api/companies/favorites/<favorite_id>/
    """
    try:
        from django.apps import apps as django_apps
        FavoriteModel = django_apps.get_model('apps', 'Favorite')
        
        # favorite_id 유효성 검사
        try:
            favorite_id = int(favorite_id)
        except (ValueError, TypeError):
            return Response(
                {'error': f'유효하지 않은 즐겨찾기 ID입니다: {favorite_id}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 즐겨찾기 확인
        try:
            favorite = FavoriteModel.objects.get(id=favorite_id)
        except FavoriteModel.DoesNotExist:
            return Response(
                {'error': f'즐겨찾기 ID {favorite_id}를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 특정 즐겨찾기만 삭제 (해당 그룹에서만)
        corp_code = favorite.company.corp_code
        company_name = favorite.company.company_name or ''
        group_name = favorite.group.name
        favorite.delete()
        
        return Response({
            'id': favorite_id,
            'corp_code': corp_code,
            'company_name': company_name,
            'group_name': group_name,
            'message': '즐겨찾기에서 삭제되었습니다.'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
def change_favorite_group(request, favorite_id):
    """
    즐겨찾기 그룹 변경 API
    PUT /api/companies/favorites/<favorite_id>/group/
    
    Body: {"group_id": 2}
    """
    try:
        from django.apps import apps as django_apps
        FavoriteGroupModel = django_apps.get_model('apps', 'FavoriteGroup')
        FavoriteModel = django_apps.get_model('apps', 'Favorite')
        
        # 즐겨찾기 확인
        try:
            favorite = FavoriteModel.objects.get(id=favorite_id)
        except FavoriteModel.DoesNotExist:
            return Response(
                {'error': f'즐겨찾기 ID {favorite_id}를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 그룹 ID 확인
        group_id = request.data.get('group_id')
        if not group_id:
            return Response(
                {'error': 'group_id가 필요합니다.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            group_id = int(group_id)
        except (ValueError, TypeError):
            return Response(
                {'error': 'group_id는 정수여야 합니다.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 그룹 확인
        try:
            group = FavoriteGroupModel.objects.get(id=group_id)
        except FavoriteGroupModel.DoesNotExist:
            return Response(
                {'error': f'그룹 ID {group_id}를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 같은 그룹이면 변경 불필요
        if favorite.group.id == group_id:
            return Response({
                'id': favorite.id,
                'corp_code': favorite.company.corp_code,
                'company_name': favorite.company.company_name or '',
                'group_id': group.id,
                'group_name': group.name
            }, status=status.HTTP_200_OK)
        
        # 같은 그룹에 같은 기업이 이미 있는지 확인
        if FavoriteModel.objects.filter(group=group, company=favorite.company).exists():
            return Response(
                {'error': '해당 그룹에 이미 같은 기업이 있습니다.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 그룹 변경
        favorite.group = group
        favorite.save()
        
        return Response({
            'id': favorite.id,
            'corp_code': favorite.company.corp_code,
            'company_name': favorite.company.company_name or '',
            'group_id': group.id,
            'group_name': group.name
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET', 'POST'])
def favorite_groups(request):
    """
    즐겨찾기 그룹 목록 조회 및 생성 API
    GET /api/companies/favorite-groups/ - 그룹 목록 조회
    POST /api/companies/favorite-groups/ - 그룹 생성
    """
    try:
        from django.apps import apps as django_apps
        FavoriteGroupModel = django_apps.get_model('apps', 'FavoriteGroup')
        
        if request.method == 'GET':
            groups = FavoriteGroupModel.objects.all().order_by('name')
            return Response({
                'groups': [
                    {
                        'id': group.id,
                        'name': group.name,
                        'created_at': group.created_at.isoformat() if group.created_at else None
                    }
                    for group in groups
                ]
            }, status=status.HTTP_200_OK)
        elif request.method == 'POST':
            name = request.data.get('name', '').strip()
            if not name:
                return Response(
                    {'error': '그룹명이 필요합니다.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 중복 확인
            if FavoriteGroupModel.objects.filter(name=name).exists():
                return Response(
                    {'error': '이미 같은 이름의 그룹이 있습니다.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 그룹 생성
            group = FavoriteGroupModel.objects.create(name=name)
            
            return Response({
                'id': group.id,
                'name': group.name,
                'created_at': group.created_at.isoformat() if group.created_at else None
            }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT', 'DELETE'])
def favorite_group_detail(request, group_id):
    """
    즐겨찾기 그룹 수정 및 삭제 API
    PUT /api/companies/favorite-groups/<group_id>/ - 그룹 수정
    DELETE /api/companies/favorite-groups/<group_id>/ - 그룹 삭제
    """
    try:
        from django.apps import apps as django_apps
        FavoriteGroupModel = django_apps.get_model('apps', 'FavoriteGroup')
        
        # 그룹 확인
        try:
            group = FavoriteGroupModel.objects.get(id=group_id)
        except FavoriteGroupModel.DoesNotExist:
            return Response(
                {'error': f'그룹 ID {group_id}를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if request.method == 'PUT':
            name = request.data.get('name', '').strip()
            if not name:
                return Response(
                    {'error': '그룹명이 필요합니다.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 중복 확인 (자기 자신 제외)
            if FavoriteGroupModel.objects.filter(name=name).exclude(id=group_id).exists():
                return Response(
                    {'error': '이미 같은 이름의 그룹이 있습니다.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 그룹명 수정
            group.name = name
            group.save()
            
            return Response({
                'id': group.id,
                'name': group.name,
                'created_at': group.created_at.isoformat() if group.created_at else None,
                'updated_at': group.updated_at.isoformat() if group.updated_at else None
            }, status=status.HTTP_200_OK)
        elif request.method == 'DELETE':
            # 그룹 삭제 (CASCADE로 즐겨찾기도 함께 삭제됨)
            group_name = group.name
            group.delete()
            
            return Response({
                'id': group_id,
                'name': group_name,
                'message': '그룹이 삭제되었습니다.'
            }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def collect_quarterly_reports(request, corp_code):
    """
    최근 분기보고서 수집 API
    POST /api/companies/{corp_code}/quarterly-reports/collect/
    
    가장 최근 사업보고서 이후의 분기보고서를 수집하여 DB에 저장합니다.
    
    corp_code는 기업번호(8자리) 또는 종목코드(6자리)를 받을 수 있습니다.
    """
    try:
        from apps.dart.client import DartClient
        from apps.service.dart import DartDataService
        from apps.service.calculator import IndicatorCalculator
        from django.apps import apps as django_apps
        from django.utils import timezone
        from django.db import transaction
        
        # 종목코드인지 기업번호인지 확인
        if len(corp_code) == 6 and corp_code.isdigit():
            dart_client = DartClient()
            converted_corp_code = dart_client._get_corp_code_by_stock_code(corp_code)
            if not converted_corp_code:
                return Response(
                    {'error': f'종목코드 {corp_code}에 해당하는 기업번호를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            corp_code = converted_corp_code
        
        CompanyModel = django_apps.get_model('apps', 'Company')
        QuarterlyFinancialDataModel = django_apps.get_model('apps', 'QuarterlyFinancialData')
        
        # 기업 존재 확인
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
        except CompanyModel.DoesNotExist:
            return Response(
                {'error': '기업을 찾을 수 없습니다. 먼저 연도별 데이터를 수집해주세요.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # DART 클라이언트 및 서비스 초기화
        dart_client = DartClient()
        dart_service = DartDataService()
        
        # 가장 최근 사업보고서 접수일자 조회
        latest_annual_date = dart_client.get_latest_annual_report_date(corp_code)
        
        if not latest_annual_date:
            return Response(
                {'error': '최근 사업보고서를 찾을 수 없습니다.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # 해당 날짜 이후의 분기보고서 목록 조회
        quarterly_reports = dart_client.get_quarterly_reports_after_date(corp_code, latest_annual_date)
        
        if not quarterly_reports:
            return Response(
                {'message': '최근 사업보고서 이후의 분기보고서가 없습니다.', 'collected_count': 0},
                status=status.HTTP_200_OK
            )
        
        # 분기보고서 데이터 수집
        quarterly_data_list = dart_service.collect_quarterly_financial_data(corp_code, quarterly_reports)
        
        # DB에 저장
        collected_count = 0
        now = timezone.now()
        
        with transaction.atomic():
            for year, quarter, quarterly_data, rcept_no in quarterly_data_list:
                # 기본 재무지표 계산 (영업이익률만, ROE는 계산하지 않음)
                IndicatorCalculator.calculate_basic_financial_ratios_for_quarterly(quarterly_data)
                
                # 해당 분기보고서의 reprt_code 찾기
                reprt_code = None
                for report in quarterly_reports:
                    if report.get('rcept_no') == rcept_no:
                        reprt_code = report.get('reprt_code', '')
                        break
                
                # DB에 저장 (ROE는 저장하지 않음, 0.0으로 유지)
                QuarterlyFinancialDataModel.objects.update_or_create(
                    company=company,
                    year=year,
                    quarter=quarter,
                    defaults={
                        'reprt_code': reprt_code or '',
                        'rcept_no': rcept_no,
                        'revenue': quarterly_data.revenue,
                        'operating_income': quarterly_data.operating_income,
                        'net_income': quarterly_data.net_income,
                        'total_assets': quarterly_data.total_assets,
                        'total_equity': quarterly_data.total_equity,
                        'operating_margin': quarterly_data.operating_margin,
                        'roe': 0.0,  # 분기보고서에서는 ROE 계산하지 않음
                        'collected_at': now,
                    }
                )
                collected_count += 1
        
        return Response({
            'message': f'{collected_count}개의 분기보고서를 수집했습니다.',
            'collected_count': collected_count,
            'quarterly_reports': [
                {
                    'year': year,
                    'quarter': quarter,
                    'rcept_no': rcept_no,
                }
                for year, quarter, _, rcept_no in quarterly_data_list
            ]
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_quarterly_financial_data(request, corp_code):
    """
    분기보고서 재무 데이터 조회 API
    GET /api/companies/{corp_code}/quarterly-data/
    
    DB에 저장된 분기보고서 데이터를 조회합니다.
    
    corp_code는 기업번호(8자리) 또는 종목코드(6자리)를 받을 수 있습니다.
    """
    try:
        from django.apps import apps as django_apps
        
        # 종목코드인지 기업번호인지 확인
        if len(corp_code) == 6 and corp_code.isdigit():
            from apps.dart.client import DartClient
            dart_client = DartClient()
            converted_corp_code = dart_client._get_corp_code_by_stock_code(corp_code)
            if not converted_corp_code:
                return Response(
                    {'error': f'종목코드 {corp_code}에 해당하는 기업번호를 찾을 수 없습니다.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            corp_code = converted_corp_code
        
        CompanyModel = django_apps.get_model('apps', 'Company')
        QuarterlyFinancialDataModel = django_apps.get_model('apps', 'QuarterlyFinancialData')
        
        # Company 먼저 조회 (인덱스 활용, JOIN 최소화)
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
        except CompanyModel.DoesNotExist:
            # 기업이 없으면 빈 결과 반환
            return Response({
                'quarterly_data': []
            }, status=status.HTTP_200_OK)
        
        # company_id로 직접 조회 (인덱스 활용, JOIN 없음)
        quarterly_data_list = QuarterlyFinancialDataModel.objects.filter(
            company=company
        ).order_by('-year', '-quarter')
        
        quarterly_data = [
            {
                'year': qd.year,
                'quarter': qd.quarter,
                'reprt_code': qd.reprt_code,
                'rcept_no': qd.rcept_no,
                'revenue': qd.revenue,
                'operating_income': qd.operating_income,
                'net_income': qd.net_income,
                'total_assets': qd.total_assets,
                'total_equity': qd.total_equity,
                'operating_margin': qd.operating_margin,
                'roe': qd.roe,
                'collected_at': qd.collected_at.isoformat() if qd.collected_at else None,
            }
            for qd in quarterly_data_list
        ]
        
        return Response({
            'quarterly_data': quarterly_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

