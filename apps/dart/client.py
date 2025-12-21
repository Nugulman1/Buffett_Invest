"""
DART OpenDART API 클라이언트
"""
import requests
from django.conf import settings


class DartClient:
    """DART OpenDART API 클라이언트"""
    
    BASE_URL = "https://opendart.fss.or.kr/api"
    
    def __init__(self, api_key=None):
        """
        DART 클라이언트 초기화
        
        Args:
            api_key: DART API 키 (없으면 settings에서 가져옴)
        """
        self.api_key = api_key or settings.DART_API_KEY
        if not self.api_key:
            raise ValueError("DART_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    
    def _make_request(self, endpoint, params=None):
        """
        API 요청 공통 메서드
        
        Args:
            endpoint: API 엔드포인트
            params: 요청 파라미터
            
        Returns:
            API 응답 데이터
        """
        url = f"{self.BASE_URL}/{endpoint}"
        
        if params is None:
            params = {}
        
        params['crtfc_key'] = self.api_key
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"DART API 요청 실패: {str(e)}")
    
    def get_company_info(self, corp_code):
        """
        기업 정보 조회
        
        Args:
            corp_code: 고유번호 (8자리)
            
        Returns:
            기업 정보 데이터
        """
        return self._make_request("company.json", params={'corp_code': corp_code})
    
    # 향후 필요한 메서드들을 여기에 추가
    # 예: 재무제표 조회, 공시 정보 조회 등

