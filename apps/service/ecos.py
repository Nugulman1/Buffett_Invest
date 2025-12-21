"""
ECOS 데이터 수집 서비스
"""
from apps.ecos.client import EcosClient


class EcosDataService:
    """ECOS API를 통한 국채 금리 데이터 수집"""
    
    def __init__(self):
        self.client = EcosClient()
    
    def collect_bond_yield_5y(self, date=None):
        """
        국채 5년 수익률 데이터 수집 (당일)
        
        Args:
            date: 조회일자 (YYYYMMDD 형식, None이면 오늘 날짜)
        
        Returns:
            국채 5년 수익률 (float, %)
        """
        try:
            bond_yield = self.client.get_bond_yield_5y(date)
            return bond_yield
        except Exception as e:
            raise Exception(f"국채 5년 수익률 수집 실패: {str(e)}")


