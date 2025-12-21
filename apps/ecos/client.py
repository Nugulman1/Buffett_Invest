"""
ECOS 한국은행 경제통계시스템 API 클라이언트
국채 금리 데이터 조회
"""
import requests
from django.conf import settings


class EcosClient:
    """ECOS 한국은행 경제통계시스템 API 클라이언트"""
    
    BASE_URL = "https://ecos.bok.or.kr/api"
    
    def __init__(self, api_key=None):
        """
        ECOS 클라이언트 초기화
        
        Args:
            api_key: ECOS API 키 (없으면 settings에서 가져옴)
        """
        self.api_key = api_key or settings.ECOS_API_KEY
        if not self.api_key:
            raise ValueError("ECOS_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
    
    def _make_request(self, stat_code, item_code1, item_code2=None, start_date=None, end_date=None, cycle='D'):
        """
        API 요청 공통 메서드
        
        Args:
            stat_code: 통계표코드
            item_code1: 통계항목코드1
            item_code2: 통계항목코드2 (선택)
            start_date: 시작일자 (YYYYMMDD 형식)
            end_date: 종료일자 (YYYYMMDD 형식)
            cycle: 주기 (D: 일별, W: 주별, M: 월별, Q: 분기별, Y: 연간)
            
        Returns:
            API 응답 데이터
        """
        # ECOS API URL 구조: /{API_NAME}/{API_KEY}/{FORMAT}/{LANG}/{START}/{END}/{STAT_CODE}/{CYCLE}/{START_DATE}/{END_DATE}/{ITEM_CODE}
        url = f"{self.BASE_URL}/StatisticSearch/{self.api_key}/json/kr/1/1000/{stat_code}"
        
        # 주기와 날짜를 먼저 추가
        if start_date and end_date:
            url += f"/{cycle}/{start_date}/{end_date}"
        elif start_date:
            url += f"/{cycle}/{start_date}/{start_date}"
        
        # 통계항목코드를 마지막에 추가
        url += f"/{item_code1}"
        
        if item_code2:
            url += f"/{item_code2}"
        
        params = {}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"ECOS API 요청 실패: {str(e)}")
    
   
    def get_bond_yield_5y(self, date=None):
        """
        국채 5년 수익률 조회 (월)
        
        Args:
            date: 조회일자 (YYYYMMDD 형식, None이면 오늘 날짜 기준 이전 달)
            
        Returns:
            국채 5년 수익률 데이터
        """
        from datetime import datetime
        
        # 날짜가 없으면 오늘 날짜 사용
        if date is None:
            target_date = datetime.now()
        else:
            # YYYYMMDD -> datetime 변환
            target_date = datetime.strptime(date, '%Y%m%d')
        
        # 입력된 날짜(또는 오늘)의 이전 달 계산
        year = target_date.year
        month = target_date.month
        
        # 월이 1월이면 작년 12월로, 아니면 같은 해의 (월-1)월
        if month == 1:
            year -= 1
            month = 12
        else:
            month -= 1
        
        date_month = f"{year:04d}{month:02d}"
        
        # 월 국채 5년 수익률
        stat_code = "721Y001"
        item_code1 = "5040000"
        
        result = self._make_request(stat_code, item_code1, start_date=date_month, end_date=date_month, cycle='M')
        
        # 응답 데이터 파싱
        if result.get('StatisticSearch'):
            row = result['StatisticSearch'].get('row', [])
            
            if row and len(row) > 0:
                # DATA_VALUE를 직접 찾기 (row 배열에서 DATA_VALUE가 있는 항목 찾기)
                data_value = None
                for item in row:
                    if isinstance(item, dict) and 'DATA_VALUE' in item:
                        data_value = item.get('DATA_VALUE', '0')
                        break
            
                return float(data_value)
        
        return 0.0

