"""
DART API 뷰
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .client import DartClient


@api_view(['GET'])
def company_info(request, corp_code):
    """
    기업 정보 조회 API
    
    GET /api/dart/company/{corp_code}/
    """
    try:
        client = DartClient()
        data = client.get_company_info(corp_code)
        return Response(data, status=status.HTTP_200_OK)
    except ValueError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

