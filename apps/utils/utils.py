"""
재무제표 데이터 정규화 유틸리티
"""
from apps.models import CompanyFinancialObject


def normalize_account_name(account_name: str) -> str:
    """
    계정명 정규화 함수
    
    계정명 매칭을 위한 전처리:
    - 공백 제거
    - 괄호 정리 (중복 괄호 처리 등)
    
    Args:
        account_name: 원본 계정명
        
    Returns:
        정규화된 계정명
    """
    if not account_name:
        return ""
    
    # 공백 제거
    normalized = account_name.strip()
    
    # 괄호 정리 (중복 괄호 처리)
    # 예: "당기순이익(손실)" -> "당기순이익(손실)"
    # 예: "영업이익(손실) (연결)" -> "영업이익(손실)(연결)"
    normalized = normalized.replace(" (", "(").replace(") ", ")")
    
    return normalized


def print_latest_year_indicators(company_data: CompanyFinancialObject):
    """
    CompanyFinancialObject의 가장 최근 년도 지표 데이터를 출력 (수집 확인용)
    
    Args:
        company_data: CompanyFinancialObject 객체
    """
    if not company_data.yearly_data:
        print("경고: 수집된 데이터가 없습니다.")
        return
    
    # 가장 최근 년도 찾기
    latest_data = max(company_data.yearly_data, key=lambda x: x.year)
    
    print("=" * 80)
    print(f"회사 정보: {company_data.company_name} ({company_data.corp_code})")
    print(f"가장 최근 년도: {latest_data.year}년")
    if company_data.bond_yield_5y > 0:
        print(f"채권수익률 (5년): {company_data.bond_yield_5y:.2f}%")
    else:
        print(f"채권수익률 (5년): 수집되지 않음")
    print("=" * 80)
    print("\n[기본 지표]")
    print(f"  자산총계: {latest_data.total_assets:,} 원")
    print(f"  영업이익: {latest_data.operating_income:,} 원")
    print(f"  당기순이익: {latest_data.net_income:,} 원")
    print(f"  유동부채: {latest_data.current_liabilities:,} 원")
    print(f"  이자부유동부채: {latest_data.interest_bearing_current_liabilities:,} 원")
    print(f"  유형자산 취득: {latest_data.tangible_asset_acquisition:,} 원")
    print(f"  무형자산 취득: {latest_data.intangible_asset_acquisition:,} 원")
    print(f"  CFO (영업활동현금흐름): {latest_data.cfo:,} 원")
    print(f"  이자비용: {latest_data.interest_expense:,} 원")
    print(f"  베타: {latest_data.beta}")
    print(f"  MRP: {latest_data.mrp}%")
    
    print("\n[계산된 지표]")
    print(f"  FCF (자유현금흐름): {latest_data.fcf:,} 원")
    print(f"  ICR (이자보상비율): {latest_data.icr:.2f}")
    print(f"  ROIC (투하자본수익률): {latest_data.roic:.2f}%")
    print(f"  WACC (가중평균자본비용): {latest_data.wacc:.2f}%")
    
    print("\n[전체 년도 목록]")
    for yearly_data in sorted(company_data.yearly_data, key=lambda x: x.year, reverse=True):
        print(f"  {yearly_data.year}년: 자산총계={yearly_data.total_assets:,}, 영업이익={yearly_data.operating_income:,}")
    print("=" * 80)

