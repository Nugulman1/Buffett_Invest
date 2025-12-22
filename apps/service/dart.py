"""
DART 데이터 수집 서비스
"""
from datetime import datetime
from apps.dart.client import DartClient
from apps.models import FinancialStatementData


class DartDataService:
    """DART API를 통한 재무제표 데이터 수집"""
    
    def __init__(self):
        self.client = DartClient()
    
    def _get_recent_years(self, count=5):
        """
        최근 N년 연도 리스트 반환
        연간보고서는 다음 해에 발행되므로:
        - 현재 월이 4월 이상이면: (현재연도-5) ~ (현재연도-1)
        - 현재 월이 1~3월이면: (현재연도-6) ~ (현재연도-2)
        
        Args:
            count: 수집할 연도 수 (기본값: 5)
            
        Returns:
            연도 리스트 (예: [2020, 2021, 2022, 2023, 2024])
        """
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        if current_month >= 4:
            # 4월 이후: 올해 연도까지 포함 가능
            start_year = current_year - count
            end_year = current_year - 1
        else:
            # 1~3월: 작년 연도까지만 포함 가능
            start_year = current_year - count - 1
            end_year = current_year - 2
        
        return list(range(start_year, end_year))
    
    def collect_financial_data(self, corp_code, years=None):
        """
        최근 5년 연간 보고서 재무제표 데이터 수집
        
        Args:
            corp_code: 고유번호 (8자리)
            years: 수집할 연도 리스트 (None이면 자동 계산)
        
        Returns:
            FinancialStatementData 객체 리스트 (연도별)
        """
        if years is None:
            years = self._get_recent_years(5)
        
        financial_statements = []
        
        for year in years:
            year_str = str(year)
            
            # 연결재무제표 우선 시도, 없으면 별도재무제표
            for fs_div in ['CFS', 'OFS']:
                try:
                    # 재무제표 조회
                    raw_data = self.client.get_financial_statement(
                        corp_code=corp_code,
                        bsns_year=year_str,
                        reprt_code='11011',  # 사업보고서
                        fs_div=fs_div
                    )
                    
                    if raw_data:
                        # FinancialStatementData 객체 생성
                        fs_data = FinancialStatementData(
                            year=year_str,
                            reprt_code='11011',
                            fs_div=fs_div,
                            raw_data=raw_data
                        )
                        financial_statements.append(fs_data)
                        break  # 성공하면 다음 연도로
                        
                except Exception as e:
                    # 연결재무제표 실패 시 별도재무제표 시도
                    if fs_div == 'CFS':
                        continue
                    else:
                        # 둘 다 실패하면 해당 연도는 스킵
                        print(f"경고: {year}년 재무제표 수집 실패: {e}")
                        break
        
        return financial_statements


