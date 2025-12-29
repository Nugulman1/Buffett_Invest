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
    - 영어 소문자 변환
    
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
    
    # 영어 소문자 변환
    normalized = normalized.lower()
    
    return normalized


def normalize_acode(acode: str) -> str:
    """
    ACODE 정규화 함수
    
    XBRL ACODE 매칭을 위한 전처리:
    - 콜론(:)을 언더스코어(_)로 변환
    - 영어 소문자 변환
    
    Args:
        acode: 원본 ACODE (예: "ifrs-full:CurrentPortionOfLongTermBorrowings")
        
    Returns:
        정규화된 ACODE (예: "ifrs-full_currentportionoflongtermborrowings")
    """
    if not acode:
        return ""
    
    # 콜론을 언더스코어로 변환
    normalized = acode.replace(":", "_")
    
    # 영어 소문자 변환
    normalized = normalized.lower()
    
    return normalized


def format_amount_korean(amount: int) -> str:
    """
    금액을 조, 억, 만 단위로 보기 쉽게 포맷팅
    
    Args:
        amount: 금액 (정수)
        
    Returns:
        포맷팅된 문자열 (예: "514조 5,319억 4,800만원")
    """
    if amount == 0:
        return "0원"
    
    # 음수 처리
    is_negative = amount < 0
    amount = abs(amount)
    
    # 조, 억, 만 단위 계산
    cho = amount // 1_000_000_000_000  # 조
    eok = (amount % 1_000_000_000_000) // 100_000_000  # 억
    man = (amount % 100_000_000) // 10_000  # 만
    remainder = amount % 10_000  # 나머지
    
    parts = []
    
    if cho > 0:
        parts.append(f"{cho:,}조")
    if eok > 0:
        parts.append(f"{eok:,}억")
    if man > 0:
        parts.append(f"{man:,}만")
    if remainder > 0:
        parts.append(f"{remainder:,}")
    
    if not parts:
        result = "0원"
    else:
        result = " ".join(parts) + "원"
    
    if is_negative:
        result = f"-{result}"
    
    return result


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
    print(f"  자산총계: {format_amount_korean(latest_data.total_assets)} ({latest_data.total_assets:,} 원)")
    print(f"  영업이익: {format_amount_korean(latest_data.operating_income)} ({latest_data.operating_income:,} 원)")
    print(f"  당기순이익: {format_amount_korean(latest_data.net_income)} ({latest_data.net_income:,} 원)")
    print(f"  유동부채: {format_amount_korean(latest_data.current_liabilities)} ({latest_data.current_liabilities:,} 원)")
    print(f"  이자부유동부채: {format_amount_korean(latest_data.interest_bearing_current_liabilities)} ({latest_data.interest_bearing_current_liabilities:,} 원)")
    print(f"  유형자산 취득: {format_amount_korean(latest_data.tangible_asset_acquisition)} ({latest_data.tangible_asset_acquisition:,} 원)")
    print(f"  무형자산 취득: {format_amount_korean(latest_data.intangible_asset_acquisition)} ({latest_data.intangible_asset_acquisition:,} 원)")
    print(f"  CFO (영업활동현금흐름): {format_amount_korean(latest_data.cfo)} ({latest_data.cfo:,} 원)")
    print(f"  이자비용: {format_amount_korean(latest_data.interest_expense)} ({latest_data.interest_expense:,} 원)")
    print(f"  자기자본: {format_amount_korean(latest_data.equity)} ({latest_data.equity:,} 원)")
    print(f"  현금및현금성자산: {format_amount_korean(latest_data.cash_and_cash_equivalents)} ({latest_data.cash_and_cash_equivalents:,} 원)")
    print(f"  단기차입금: {format_amount_korean(latest_data.short_term_borrowings)} ({latest_data.short_term_borrowings:,} 원)")
    print(f"  유동성장기차입금: {format_amount_korean(latest_data.current_portion_of_long_term_borrowings)} ({latest_data.current_portion_of_long_term_borrowings:,} 원)")
    print(f"  장기차입금: {format_amount_korean(latest_data.long_term_borrowings)} ({latest_data.long_term_borrowings:,} 원)")
    print(f"  사채: {format_amount_korean(latest_data.bonds)} ({latest_data.bonds:,} 원)")
    print(f"  리스부채: {format_amount_korean(latest_data.lease_liabilities)} ({latest_data.lease_liabilities:,} 원)")
    print(f"  베타: {latest_data.beta}")
    print(f"  MRP: {latest_data.mrp}%")
    
    print("\n[계산된 지표]")
    print(f"  FCF (자유현금흐름): {format_amount_korean(latest_data.fcf)} ({latest_data.fcf:,} 원)")
    print(f"  ICR (이자보상비율): {latest_data.icr:.2f}")
    print(f"  ROIC (투하자본수익률): {latest_data.roic:.2f}%")
    print(f"  WACC (가중평균자본비용): {latest_data.wacc:.2f}%")
    
    print("\n[전체 년도 목록]")
    for yearly_data in sorted(company_data.yearly_data, key=lambda x: x.year, reverse=True):
        print(f"  {yearly_data.year}년: 자산총계={format_amount_korean(yearly_data.total_assets)}, 영업이익={format_amount_korean(yearly_data.operating_income)}")
    print("=" * 80)

