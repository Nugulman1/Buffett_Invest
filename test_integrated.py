"""
통합 데이터 수집 테스트 스크립트
오케스트레이터를 실행하고 최근 5년의 지표를 출력합니다.
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
from apps.utils.utils import format_amount_korean


def print_all_years_data(company_data):
    """
    최근 5년의 지표 데이터를 출력
    
    Args:
        company_data: CompanyFinancialObject 객체
    """
    if not company_data.yearly_data:
        print("경고: 수집된 데이터가 없습니다.")
        return
    
    # 연도별로 정렬 (오름차순)
    sorted_data = sorted(company_data.yearly_data, key=lambda x: x.year)
    
    print("\n" + "=" * 80)
    print(f"회사 정보: {company_data.company_name} ({company_data.corp_code})")
    if company_data.bond_yield_5y > 0:
        print(f"채권수익률 (5년): {company_data.bond_yield_5y:.2f}%")
    print("=" * 80)
    
    # 연도별 지표 출력
    for yearly_data in sorted_data:
        print(f"\n[{yearly_data.year}년]")
        
        # === 기본 지표 (DART API) ===
        print("  [기본 지표]")
        print(f"    매출액: {format_amount_korean(yearly_data.revenue)} ({yearly_data.revenue:,} 원)")
        print(f"    영업이익: {format_amount_korean(yearly_data.operating_income)} ({yearly_data.operating_income:,} 원)")
        print(f"    당기순이익: {format_amount_korean(yearly_data.net_income)} ({yearly_data.net_income:,} 원)")
        print(f"    자산총계: {format_amount_korean(yearly_data.total_assets)} ({yearly_data.total_assets:,} 원)")
        print(f"    자본총계: {format_amount_korean(yearly_data.total_equity)} ({yearly_data.total_equity:,} 원)")
        # 매출총이익률, 판관비율은 더 이상 수집하지 않음 (기본 지표 API에 해당 계정이 없음)
        # print(f"    매출총이익률: {yearly_data.gross_profit_margin:.2f}%")  # 수집 안 함
        # print(f"    판관비율: {yearly_data.selling_admin_expense_ratio:.2f}%")  # 수집 안 함
        # 계산 방식으로 변경된 재무지표
        print(f"    총자산영업이익률 (계산): {yearly_data.total_assets_operating_income_ratio:.2f}%")
        print(f"    ROE (계산): {yearly_data.roe:.2f}%")
        
        # === 계산에 사용하는 기본 지표 (XBRL) ===
        # XBRL 데이터 수집 중단으로 주석처리
        # print("\n  [계산에 사용하는 기본 지표 (XBRL)]")
        # print(f"    금융비용: {format_amount_korean(yearly_data.finance_costs)} ({yearly_data.finance_costs:,} 원)")
        # print(f"    유형자산 취득: {format_amount_korean(yearly_data.tangible_asset_acquisition)} ({yearly_data.tangible_asset_acquisition:,} 원)")
        # print(f"    무형자산 취득: {format_amount_korean(yearly_data.intangible_asset_acquisition)} ({yearly_data.intangible_asset_acquisition:,} 원)")
        # print(f"    CFO (영업활동현금흐름): {format_amount_korean(yearly_data.cfo)} ({yearly_data.cfo:,} 원)")
        # print(f"    자기자본: {format_amount_korean(yearly_data.equity)} ({yearly_data.equity:,} 원)")
        # print(f"    현금및현금성자산: {format_amount_korean(yearly_data.cash_and_cash_equivalents)} ({yearly_data.cash_and_cash_equivalents:,} 원)")
        # print(f"    단기차입금: {format_amount_korean(yearly_data.short_term_borrowings)} ({yearly_data.short_term_borrowings:,} 원)")
        # print(f"    유동성장기차입금: {format_amount_korean(yearly_data.current_portion_of_long_term_borrowings)} ({yearly_data.current_portion_of_long_term_borrowings:,} 원)")
        # print(f"    장기차입금: {format_amount_korean(yearly_data.long_term_borrowings)} ({yearly_data.long_term_borrowings:,} 원)")
        # print(f"    사채: {format_amount_korean(yearly_data.bonds)} ({yearly_data.bonds:,} 원)")
        # print(f"    리스부채: {format_amount_korean(yearly_data.lease_liabilities)} ({yearly_data.lease_liabilities:,} 원)")
        
        # === 계산된 지표 (XBRL 기반) ===
        # XBRL 데이터 수집 중단으로 주석처리
        # print("\n  [계산된 지표]")
        # print(f"    FCF (자유현금흐름): {format_amount_korean(yearly_data.fcf)} ({yearly_data.fcf:,} 원)")
        # print(f"    ICR (이자보상비율): {yearly_data.icr:.2f}")
        # print(f"    ROIC (투하자본수익률): {yearly_data.roic:.2f}%")
        # print(f"    WACC (가중평균자본비용): {yearly_data.wacc:.2f}%")
    
    # === 필터 결과 ===
    print("\n" + "=" * 80)
    print("[필터 결과]")
    print(f"  전체 필터 통과: {'✓ 통과' if company_data.passed_all_filters else '✗ 실패'}")
    print(f"  영업이익 필터: {'✓ 통과' if company_data.filter_operating_income else '✗ 실패'}")
    print(f"  당기순이익 필터: {'✓ 통과' if company_data.filter_net_income else '✗ 실패'}")
    print(f"  매출액 CAGR 필터: {'✓ 통과' if company_data.filter_revenue_cagr else '✗ 실패'}")
    print(f"  총자산영업이익률 필터: {'✓ 통과' if company_data.filter_total_assets_operating_income_ratio else '✗ 실패'}")
    print("=" * 80)


def test_data_collection(stock_code: str = None, corp_code: str = None):
    """
    데이터 수집 테스트
    
    Args:
        stock_code: 종목코드 (6자리, 예: '005930') - stock_code 또는 corp_code 중 하나 필수
        corp_code: 고유번호 (8자리) - stock_code 또는 corp_code 중 하나 필수
    """
    print("=" * 80)
    print("통합 데이터 수집 테스트")
    print("=" * 80)
    
    try:
        orchestrator = DataOrchestrator()
        dart_client = orchestrator.dart_client
        
        # 1. 기업 정보 조회
        if stock_code:
            print(f"\n[1단계] 종목코드 {stock_code}로 기업 정보 조회...")
            company_info = dart_client.get_company_basic_info(stock_code)
            corp_code = company_info['corp_code']
            corp_name = company_info['corp_name']
            print(f"  ✓ 기업명: {corp_name}")
            print(f"  ✓ 고유번호: {corp_code}")
        elif corp_code:
            print(f"\n[1단계] 고유번호 {corp_code}로 기업 정보 조회...")
            company_info = dart_client.get_company_info(corp_code)
            corp_name = company_info.get('corp_name', '')
            print(f"  ✓ 기업명: {corp_name}")
            print(f"  ✓ 고유번호: {corp_code}")
        else:
            raise ValueError("stock_code 또는 corp_code 중 하나는 필수입니다.")
        
        # 2. 데이터 수집
        print(f"\n[2단계] 재무제표 데이터 수집 중...")
        company_data = orchestrator.collect_company_data(corp_code)
        
        print(f"  ✓ 데이터 수집 완료")
        print(f"  ✓ 수집된 연도 수: {len(company_data.yearly_data)}개")
        
        # 3. 최근 5년 지표 출력
        print(f"\n[3단계] 최근 5년 지표 출력")
        print_all_years_data(company_data)
        
        print("\n테스트 완료!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='통합 데이터 수집 테스트')
    parser.add_argument('--stock-code', type=str, help='종목코드 (6자리, 예: 005930)')
    parser.add_argument('--corp-code', type=str, help='고유번호 (8자리)')
    
    args = parser.parse_args()
    
    if not args.stock_code and not args.corp_code:
        # 기본값: 삼성전자
        test_data_collection(stock_code='005930')
    else:
        test_data_collection(stock_code=args.stock_code, corp_code=args.corp_code)

