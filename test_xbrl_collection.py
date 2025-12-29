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

from apps.service.orchestrator import DataOrchestrator
from apps.utils.utils import format_amount_korean


def test_xbrl_collection_samsung():
    """
    삼성전자 재무 데이터 수집 및 계산 테스트
    """
    print("=" * 80)
    print("재무 데이터 수집 및 계산 테스트: 삼성전자 (005930)")
    print("=" * 80)
    
    try:
        orchestrator = DataOrchestrator()
        
        # 1. 삼성전자 정보 조회
        print("\n[1단계] 삼성전자 기업 정보 조회...")
        company_info = orchestrator.dart_client.get_company_basic_info('005930')
        corp_code = company_info['corp_code']
        corp_name = company_info['corp_name']
        
        print(f"  ✓ 기업명: {corp_name}")
        print(f"  ✓ 고유번호: {corp_code}")
        
        # 2. 데이터 수집 및 계산
        print("\n[2단계] 데이터 수집 및 계산 중...")
        company_data = orchestrator.collect_company_data(corp_code)
        
        print(f"  ✓ 데이터 수집 완료")
        print(f"  ✓ 수집된 연도 수: {len(company_data.yearly_data)}개")
        if company_data.bond_yield_5y > 0:
            print(f"  ✓ 채권수익률 (5년): {company_data.bond_yield_5y:.2f}%")
        
        # 3. 수집된 데이터 출력 (계산에 사용하는 기본 지표 + 계산된 지표만)
        print("\n[3단계] 수집된 데이터 및 계산 결과 확인")
        print("=" * 80)
        
        if not company_data.yearly_data:
            print("경고: 수집된 데이터가 없습니다.")
            return
        
        for yearly_data in sorted(company_data.yearly_data, key=lambda x: x.year, reverse=True):
            print(f"\n[{yearly_data.year}년 데이터]")
            
            # === 계산에 사용하는 기본 지표 ===
            print("\n[기본 지표]")
            if company_data.bond_yield_5y > 0:
                print(f"  채권수익률 (5년): {company_data.bond_yield_5y:.2f}%")
            print(f"  영업이익: {format_amount_korean(yearly_data.operating_income)} ({yearly_data.operating_income:,} 원)")
            print(f"  금융비용: {format_amount_korean(yearly_data.finance_costs)} ({yearly_data.finance_costs:,} 원)")
            print(f"  유형자산 취득: {format_amount_korean(yearly_data.tangible_asset_acquisition)} ({yearly_data.tangible_asset_acquisition:,} 원)")
            print(f"  무형자산 취득: {format_amount_korean(yearly_data.intangible_asset_acquisition)} ({yearly_data.intangible_asset_acquisition:,} 원)")
            print(f"  CFO (영업활동현금흐름): {format_amount_korean(yearly_data.cfo)} ({yearly_data.cfo:,} 원)")
            print(f"  자기자본: {format_amount_korean(yearly_data.equity)} ({yearly_data.equity:,} 원)")
            print(f"  현금및현금성자산: {format_amount_korean(yearly_data.cash_and_cash_equivalents)} ({yearly_data.cash_and_cash_equivalents:,} 원)")
            print(f"  단기차입금: {format_amount_korean(yearly_data.short_term_borrowings)} ({yearly_data.short_term_borrowings:,} 원)")
            print(f"  유동성장기차입금: {format_amount_korean(yearly_data.current_portion_of_long_term_borrowings)} ({yearly_data.current_portion_of_long_term_borrowings:,} 원)")
            print(f"  장기차입금: {format_amount_korean(yearly_data.long_term_borrowings)} ({yearly_data.long_term_borrowings:,} 원)")
            print(f"  사채: {format_amount_korean(yearly_data.bonds)} ({yearly_data.bonds:,} 원)")
            print(f"  리스부채: {format_amount_korean(yearly_data.lease_liabilities)} ({yearly_data.lease_liabilities:,} 원)")
            
            # === 계산된 지표 ===
            print("\n[계산된 지표]")
            print(f"  FCF (자유현금흐름): {format_amount_korean(yearly_data.fcf)} ({yearly_data.fcf:,} 원)")
            print(f"  ROIC (투하자본수익률): {yearly_data.roic:.2f}%")
            print(f"  WACC (가중평균자본비용): {yearly_data.wacc:.2f}%")
        
        print("\n" + "=" * 80)
        print("테스트 완료!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()
        
if __name__ == "__main__":
    test_xbrl_collection_samsung()