"""
XBRL 데이터 수집 테스트 스크립트 (삼성전자 기준)
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
from apps.service.dart import DartDataService
from apps.service.xbrl_parser import XbrlParser
from apps.models import CompanyFinancialObject
from apps.utils.utils import format_amount_korean


def test_xbrl_collection_samsung():
    """
    삼성전자 XBRL 데이터 수집 테스트
    """
    print("=" * 80)
    print("XBRL 데이터 수집 테스트: 삼성전자 (005930)")
    print("=" * 80)
    
    try:
        dart_client = DartClient()
        dart_service = DartDataService()
        
        # 1. 삼성전자 정보 조회
        print("\n[1단계] 삼성전자 기업 정보 조회...")
        company_info = dart_client.get_company_basic_info('005930')
        corp_code = company_info['corp_code']
        corp_name = company_info['corp_name']
        
        print(f"  ✓ 기업명: {corp_name}")
        print(f"  ✓ 고유번호: {corp_code}")
        
        # 2. 최근 연도 리스트 생성 (테스트용으로 최근 1년만)
        print("\n[2단계] 수집할 연도 확인...")
        years = dart_service._get_recent_years(1)  # 최근 1년만 테스트
        print(f"  ✓ 수집 대상 연도: {years}")
        
        # 3. CompanyFinancialObject 생성
        company_data = CompanyFinancialObject()
        company_data.corp_code = corp_code
        company_data.company_name = corp_name
        
        # 4. XBRL 데이터 수집
        print("\n[3단계] XBRL 데이터 수집 중...")
        dart_service.collect_xbrl_indicators(corp_code, years, company_data)
        
        print(f"  ✓ XBRL 데이터 수집 완료")
        print(f"  ✓ 수집된 연도 수: {len(company_data.yearly_data)}개")
        
        # 5. 수집된 데이터 출력
        print("\n[4단계] 수집된 XBRL 데이터 확인")
        print("=" * 80)
        
        if not company_data.yearly_data:
            print("경고: 수집된 데이터가 없습니다.")
            return
        
        for yearly_data in sorted(company_data.yearly_data, key=lambda x: x.year, reverse=True):
            print(f"\n[{yearly_data.year}년 데이터]")
            print(f"  유형자산 취득: {format_amount_korean(yearly_data.tangible_asset_acquisition)}")
            print(f"    ({yearly_data.tangible_asset_acquisition:,} 원)")
            print(f"  무형자산 취득: {format_amount_korean(yearly_data.intangible_asset_acquisition)}")
            print(f"    ({yearly_data.intangible_asset_acquisition:,} 원)")
            print(f"  CFO (영업활동현금흐름): {format_amount_korean(yearly_data.cfo)}")
            print(f"    ({yearly_data.cfo:,} 원)")
            
            # 데이터 수집 여부 확인
            if yearly_data.tangible_asset_acquisition == 0:
                print("    ⚠ 유형자산 취득 데이터가 수집되지 않았습니다.")
            if yearly_data.intangible_asset_acquisition == 0:
                print("    ⚠ 무형자산 취득 데이터가 수집되지 않았습니다.")
            if yearly_data.cfo == 0:
                print("    ⚠ CFO 데이터가 수집되지 않았습니다.")
        
        print("\n" + "=" * 80)
        print("테스트 완료!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()


def test_xbrl_parser_direct():
    """
    XBRL 파서 직접 테스트 (로컬 파일 사용)
    """
    print("=" * 80)
    print("XBRL 파서 직접 테스트 (로컬 파일)")
    print("=" * 80)
    
    try:
        parser = XbrlParser()
        
        # 로컬 XBRL 파일 경로
        xbrl_file_path = Path(__file__).parent / 'samsung_2024_annual_report_xbrl' / '20250311001085.xml'
        
        if not xbrl_file_path.exists():
            print(f"경고: XBRL 파일을 찾을 수 없습니다: {xbrl_file_path}")
            return
        
        print(f"\n[1단계] XBRL 파일 로드: {xbrl_file_path}")
        with open(xbrl_file_path, 'rb') as f:
            xml_content = f.read()
        
        print(f"  ✓ 파일 크기: {len(xml_content):,} bytes")
        
        # XBRL 파싱
        print("\n[2단계] XBRL 파싱 중...")
        xbrl_data = parser.parse_xbrl_file(xml_content)
        
        print("  ✓ 파싱 완료")
        
        # 결과 출력
        print("\n[3단계] 추출된 데이터")
        print("=" * 80)
        print(f"  유형자산 취득: {format_amount_korean(xbrl_data.get('tangible_asset_acquisition', 0))}")
        print(f"    ({xbrl_data.get('tangible_asset_acquisition', 0):,} 원)")
        print(f"  무형자산 취득: {format_amount_korean(xbrl_data.get('intangible_asset_acquisition', 0))}")
        print(f"    ({xbrl_data.get('intangible_asset_acquisition', 0):,} 원)")
        print(f"  CFO: {format_amount_korean(xbrl_data.get('cfo', 0))}")
        print(f"    ({xbrl_data.get('cfo', 0):,} 원)")
        
        print("\n" + "=" * 80)
        print("테스트 완료!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='XBRL 데이터 수집 테스트')
    parser.add_argument('--mode', choices=['api', 'local'], default='api',
                        help='테스트 모드: api (API 다운로드), local (로컬 파일)')
    
    args = parser.parse_args()
    
    if args.mode == 'api':
        # API를 통한 XBRL 데이터 수집 테스트
        test_xbrl_collection_samsung()
    else:
        # 로컬 파일을 사용한 파서 테스트
        test_xbrl_parser_direct()

