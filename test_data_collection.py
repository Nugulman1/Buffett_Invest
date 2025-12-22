"""
데이터 수집 테스트 스크립트 (종목코드 기반)
"""
import os
import sys
import django
from pathlib import Path

# Windows 콘솔 인코딩 설정
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Django 설정 초기화
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.dart.client import DartClient
from apps.service.orchestrator import DataOrchestrator
from apps.utils.utils import print_latest_year_indicators


def test_data_collection_by_stock_code(stock_code: str):
    """
    종목코드로 데이터 수집 테스트
    
    Args:
        stock_code: 종목코드 (6자리, 예: '005930')
    """
    print("=" * 80)
    print(f"데이터 수집 테스트: 종목코드 {stock_code}")
    print("=" * 80)
    
    try:
        # 1. 종목코드로 corp_code 조회
        print(f"\n[1단계] 종목코드 {stock_code}로 기업 정보 조회...")
        dart_client = DartClient()
        company_info = dart_client.get_company_basic_info(stock_code)
        corp_code = company_info['corp_code']
        corp_name = company_info['corp_name']
        
        print(f"  ✓ 기업명: {corp_name}")
        print(f"  ✓ 고유번호: {corp_code}")
        
        # 2. 데이터 수집
        print(f"\n[2단계] 재무제표 데이터 수집 중...")
        orchestrator = DataOrchestrator()
        company_data = orchestrator.collect_company_data(corp_code)
        
        print(f"  ✓ 데이터 수집 완료")
        print(f"  ✓ 수집된 연도 수: {len(company_data.yearly_data)}개")
        
        # 3. 최근 년도 지표 출력
        print(f"\n[3단계] 수집된 데이터 확인")
        print_latest_year_indicators(company_data)
        
        print("\n" + "=" * 80)
        print("테스트 완료!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    # 삼성전자로 테스트
    test_data_collection_by_stock_code('005930')

