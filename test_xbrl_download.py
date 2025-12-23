"""
XBRL 다운로드 직접 테스트 스크립트
접수번호로 바로 다운로드 테스트
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
from apps.service.xbrl_parser import XbrlParser


def test_xbrl_download_by_rcept_no(rcept_no: str):
    """
    접수번호로 XBRL 다운로드 테스트
    
    Args:
        rcept_no: 접수번호 (14자리, 예: '20250311001085')
    """
    print("=" * 80)
    print(f"XBRL 다운로드 테스트: 접수번호 {rcept_no}")
    print("=" * 80)
    
    try:
        client = DartClient()
        parser = XbrlParser()
        
        # 1단계: XBRL ZIP 파일 다운로드
        print(f"\n[1단계] XBRL ZIP 파일 다운로드 중...")
        zip_data = client.download_xbrl(rcept_no)
        print(f"  ✓ 다운로드 완료: {len(zip_data):,} bytes")
        
        # 2단계: ZIP 파일에서 사업보고서 XML 추출
        print(f"\n[2단계] ZIP 파일에서 사업보고서 XML 추출 중...")
        try:
            xml_content = parser.extract_annual_report_file(zip_data)
            print(f"  ✓ XML 추출 완료: {len(xml_content):,} bytes")
        except Exception as e:
            print(f"  ❌ XML 추출 실패: {e}")
            return
        
        # 3단계: XBRL 파싱
        print(f"\n[3단계] XBRL 파싱 중...")
        try:
            xbrl_data = parser.parse_xbrl_file(xml_content)
            print(f"  ✓ 파싱 완료")
        except Exception as e:
            print(f"  ❌ 파싱 실패: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # 4단계: 추출된 데이터 출력
        print(f"\n[4단계] 추출된 데이터")
        print("=" * 80)
        from apps.utils.utils import format_amount_korean
        
        tangible = xbrl_data.get('tangible_asset_acquisition', 0)
        intangible = xbrl_data.get('intangible_asset_acquisition', 0)
        cfo = xbrl_data.get('cfo', 0)
        
        print(f"  유형자산 취득: {format_amount_korean(tangible)}")
        print(f"    ({tangible:,} 원)")
        print(f"  무형자산 취득: {format_amount_korean(intangible)}")
        print(f"    ({intangible:,} 원)")
        print(f"  CFO (영업활동현금흐름): {format_amount_korean(cfo)}")
        print(f"    ({cfo:,} 원)")
        
        # 데이터 수집 여부 확인
        if tangible == 0:
            print("    ⚠ 유형자산 취득 데이터가 수집되지 않았습니다.")
        if intangible == 0:
            print("    ⚠ 무형자산 취득 데이터가 수집되지 않았습니다.")
        if cfo == 0:
            print("    ⚠ CFO 데이터가 수집되지 않았습니다.")
        
        print("\n" + "=" * 80)
        print("테스트 완료!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='XBRL 다운로드 직접 테스트')
    parser.add_argument('rcept_no', nargs='?', default='20250311001085',
                        help='접수번호 (14자리, 기본값: 삼성전자 2024년 사업보고서)')
    
    args = parser.parse_args()
    
    test_xbrl_download_by_rcept_no(args.rcept_no)

