"""
재무제표 데이터 정규화 유틸리티
"""
from datetime import datetime, date
from django.apps import apps as django_apps
from apps.models import CompanyFinancialObject, YearlyFinancialDataObject


def is_financial_industry(induty_code: str) -> bool:
    """
    KSIC 코드로 금융업 여부 판별
    
    금융업 KSIC 코드:
    - 651: 일반 금융업
    - 659: 기타 금융업
    - 660: 보험 및 연금업
    - 671: 금융 관련 서비스업
    
    Args:
        induty_code: KSIC 업종 코드 (예: '264', '651')
        
    Returns:
        금융업 여부 (bool)
    """
    if not induty_code:
        return False
    
    # 앞 3자리로 판별
    code_prefix = str(induty_code)[:3]
    financial_codes = ['651', '659', '660', '671']
    return code_prefix in financial_codes


def classify_company_size(total_assets: int) -> str:
    """
    총자산 기준으로 기업 규모 분류
    
    분류 기준:
    - 중소기업: 총자산 < 5천억원 (5,000,000,000)
    - 대기업: 총자산 ≥ 10조원 (10,000,000,000,000)
    - 중견기업: 그 외 (5천억원 이상 10조원 미만)
    
    Args:
        total_assets: 총자산 (정수, 원 단위)
        
    Returns:
        기업 규모 ('small', 'medium', 'large')
    """
    SMALL_THRESHOLD = 5_000_000_000  # 5천억원
    LARGE_THRESHOLD = 10_000_000_000_000  # 10조원
    
    if total_assets < SMALL_THRESHOLD:
        return 'small'  # 중소기업
    elif total_assets >= LARGE_THRESHOLD:
        return 'large'  # 대기업
    else:
        return 'medium'  # 중견기업


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


def get_stock_code_by_corp_code(corp_code: str) -> str | None:
    """
    기업번호(corp_code)를 종목코드(stock_code)로 변환
    
    DartClient의 _corp_code_mapping_cache를 역방향으로 검색하여 변환합니다.
    캐시가 비어있으면 먼저 로드합니다.
    
    Args:
        corp_code: 기업번호 (8자리, 예: '00126380')
        
    Returns:
        종목코드 (6자리, 예: '005930') 또는 None (찾을 수 없는 경우)
    """
    from apps.dart.client import DartClient
    
    dart_client = DartClient()
    
    # 캐시가 비어있으면 먼저 로드
    if not dart_client._corp_code_mapping_cache:
        dart_client.load_corp_code_xml()
    
    # 역방향 검색: {stock_code: corp_code} 형태의 딕셔너리에서 corp_code로 stock_code 찾기
    for stock_code, cached_corp_code in dart_client._corp_code_mapping_cache.items():
        if cached_corp_code == corp_code:
            return stock_code
    
    return None


def should_collect_company(corp_code: str) -> bool:
    """
    기업 수집 필요 여부 확인 (4월 1일 기준)
    
    DB에 기업이 없거나, last_collected_at이 없거나, 4월 1일 기준으로 1년이 지났으면 수집 필요.
    
    Args:
        corp_code: 고유번호 (8자리)
    
    Returns:
        수집 필요 여부 (bool) - True면 수집 필요, False면 수집 불필요
    """
    CompanyModel = django_apps.get_model('apps', 'Company')
    
    try:
        company = CompanyModel.objects.get(corp_code=corp_code)
        
        # last_collected_at이 없으면 수집
        if not company.last_collected_at:
            return True
        
        # 4월 1일 기준 확인
        last_collected_date = company.last_collected_at.date()
        current_date = datetime.now().date()
        
        # 마지막 수집일 기준 4월 1일
        if last_collected_date.month >= 4:
            last_april = date(last_collected_date.year, 4, 1)
        else:
            last_april = date(last_collected_date.year - 1, 4, 1)
        
        # 현재 날짜 기준 4월 1일
        if current_date.month >= 4:
            current_april = date(current_date.year, 4, 1)
        else:
            current_april = date(current_date.year - 1, 4, 1)
        
        # 현재 기준 4월 1일 > 마지막 수집 기준 4월 1일이면 재수집
        return current_april > last_april
        
    except CompanyModel.DoesNotExist:
        # DB에 없으면 수집
        return True


def load_company_from_db(corp_code: str) -> CompanyFinancialObject | None:
    """
    DB에서 Company 및 YearlyFinancialData 모델을 조회하여 CompanyFinancialObject로 변환
    
    Args:
        corp_code: 고유번호 (8자리)
    
    Returns:
        CompanyFinancialObject 객체 (데이터가 없으면 None)
    """
    CompanyModel = django_apps.get_model('apps', 'Company')
    YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
    
    try:
        # Company 모델 조회 (prefetch_related로 N+1 쿼리 방지)
        company = CompanyModel.objects.prefetch_related('yearly_data').get(corp_code=corp_code)
        yearly_data_list = list(company.yearly_data.all().order_by('year'))
        
        # CompanyFinancialObject 생성
        company_data = CompanyFinancialObject()
        company_data.corp_code = company.corp_code
        company_data.company_name = company.company_name or ""
        company_data.business_type_code = company.business_type_code or ""
        company_data.business_type_name = company.business_type_name or ""
        company_data.bond_yield_5y = company.bond_yield_5y or 0.0
        company_data.passed_all_filters = company.passed_all_filters
        company_data.filter_operating_income = company.filter_operating_income
        company_data.filter_net_income = company.filter_net_income
        company_data.filter_revenue_cagr = company.filter_revenue_cagr
        company_data.filter_operating_margin = company.filter_operating_margin
        company_data.filter_roe = company.filter_roe
        
        # YearlyFinancialDataObject 리스트 생성
        for yearly_data_db in yearly_data_list:
            yearly_data_obj = YearlyFinancialDataObject(year=yearly_data_db.year, corp_code=corp_code)
            yearly_data_obj.revenue = yearly_data_db.revenue or 0
            yearly_data_obj.operating_income = yearly_data_db.operating_income or 0
            yearly_data_obj.net_income = yearly_data_db.net_income or 0
            yearly_data_obj.total_assets = yearly_data_db.total_assets or 0
            yearly_data_obj.total_equity = yearly_data_db.total_equity or 0
            yearly_data_obj.gross_profit_margin = yearly_data_db.gross_profit_margin or 0.0
            yearly_data_obj.selling_admin_expense_ratio = yearly_data_db.selling_admin_expense_ratio or 0.0
            yearly_data_obj.operating_margin = yearly_data_db.operating_margin or 0.0
            yearly_data_obj.roe = yearly_data_db.roe or 0.0
            yearly_data_obj.fcf = yearly_data_db.fcf
            yearly_data_obj.roic = yearly_data_db.roic
            yearly_data_obj.wacc = yearly_data_db.wacc
            
            company_data.yearly_data.append(yearly_data_obj)
        
        return company_data
        
    except CompanyModel.DoesNotExist:
        return None


def save_company_to_db(company_data: CompanyFinancialObject) -> None:
    """
    CompanyFinancialObject를 Django 모델로 변환하여 DB에 저장
    
    트랜잭션으로 원자성 보장: Company와 YearlyFinancialData 저장이 모두 성공하거나 모두 실패
    
    Args:
        company_data: CompanyFinancialObject 객체
    """
    from django.db import transaction
    from django.utils import timezone
    
    # Django 모델 가져오기
    CompanyModel = django_apps.get_model('apps', 'Company')
    YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
    
    # 현재 시간 (수집 일시)
    now = timezone.now()
    
    with transaction.atomic():
        # 기존 메모 조회 (보존용)
        try:
            existing_company = CompanyModel.objects.get(corp_code=company_data.corp_code)
            existing_memo = existing_company.memo
            existing_memo_updated_at = existing_company.memo_updated_at
        except CompanyModel.DoesNotExist:
            existing_memo = None
            existing_memo_updated_at = None
        
        # Company 모델 저장 또는 업데이트
        company, created = CompanyModel.objects.update_or_create(
            corp_code=company_data.corp_code,
            defaults={
                'company_name': company_data.company_name,
                'business_type_code': company_data.business_type_code,
                'business_type_name': company_data.business_type_name,
                'bond_yield_5y': company_data.bond_yield_5y,
                'last_collected_at': now,
                'passed_all_filters': company_data.passed_all_filters,
                'filter_operating_income': company_data.filter_operating_income,
                'filter_net_income': company_data.filter_net_income,
                'filter_revenue_cagr': company_data.filter_revenue_cagr,
                'filter_operating_margin': company_data.filter_operating_margin,
                'filter_roe': company_data.filter_roe,
                # memo와 memo_updated_at은 defaults에 포함하지 않음 (자동 보존)
            }
        )
        
        # 명시적으로 메모 보존 (기존 메모가 있으면 유지)
        if existing_memo:
            company.memo = existing_memo
            company.memo_updated_at = existing_memo_updated_at
            company.save(update_fields=['memo', 'memo_updated_at'])
        
        # YearlyFinancialData 모델 저장 또는 업데이트
        for yearly_data in company_data.yearly_data:
            YearlyFinancialDataModel.objects.update_or_create(
                company=company,
                year=yearly_data.year,
                defaults={
                    'revenue': yearly_data.revenue,
                    'operating_income': yearly_data.operating_income,
                    'net_income': yearly_data.net_income,
                    'total_assets': yearly_data.total_assets,
                    'total_equity': yearly_data.total_equity,
                    # gross_profit_margin, selling_admin_expense_ratio는 수집하지 않음 (0.0으로 저장됨)
                    'gross_profit_margin': yearly_data.gross_profit_margin,
                    'selling_admin_expense_ratio': yearly_data.selling_admin_expense_ratio,
                    # operating_margin, roe는 계산 방식으로 채워짐
                    'operating_margin': yearly_data.operating_margin,
                    'roe': yearly_data.roe,
                }
            )


def backup_company_memos(corp_code: str = None) -> dict | list | None:
    """
    기업 메모 백업
    
    Args:
        corp_code: 고유번호 (None이면 전체 기업)
    
    Returns:
        단일 기업: {'corp_code': '...', 'memo': '...', 'memo_updated_at': '...'} 또는 None (메모 없음)
        전체 기업: [{'corp_code': '...', 'memo': '...', 'memo_updated_at': '...'}, ...]
    """
    CompanyModel = django_apps.get_model('apps', 'Company')
    
    if corp_code:
        # 단일 기업 메모 백업
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
            # 메모가 있는 경우만 백업
            if company.memo:
                return {
                    'corp_code': company.corp_code,
                    'memo': company.memo,
                    'memo_updated_at': company.memo_updated_at.isoformat() if company.memo_updated_at else None
                }
            return None
        except CompanyModel.DoesNotExist:
            return None
    else:
        # 전체 기업 메모 백업
        memos = []
        for company in CompanyModel.objects.exclude(memo__isnull=True).exclude(memo=''):
            memos.append({
                'corp_code': company.corp_code,
                'memo': company.memo,
                'memo_updated_at': company.memo_updated_at.isoformat() if company.memo_updated_at else None
            })
        return memos


def restore_company_memos(memo_backup: dict | list) -> int:
    """
    기업 메모 복원
    
    Args:
        memo_backup: backup_company_memos()로 백업한 데이터
        - 단일 기업: {'corp_code': '...', 'memo': '...', 'memo_updated_at': '...'}
        - 전체 기업: [{'corp_code': '...', 'memo': '...', 'memo_updated_at': '...'}, ...]
    
    Returns:
        복원된 메모 개수
    """
    CompanyModel = django_apps.get_model('apps', 'Company')
    from django.utils import timezone
    from datetime import datetime
    
    restored_count = 0
    
    # 단일 기업 또는 전체 기업 처리
    memos_to_restore = [memo_backup] if isinstance(memo_backup, dict) else memo_backup
    
    for memo_data in memos_to_restore:
        if not memo_data or 'corp_code' not in memo_data:
            continue
        
        corp_code = memo_data['corp_code']
        memo = memo_data.get('memo', '')
        memo_updated_at_str = memo_data.get('memo_updated_at')
        
        # memo_updated_at 문자열을 datetime으로 변환
        memo_updated_at = None
        if memo_updated_at_str:
            try:
                memo_updated_at = datetime.fromisoformat(memo_updated_at_str.replace('Z', '+00:00'))
                if memo_updated_at.tzinfo is None:
                    memo_updated_at = timezone.make_aware(memo_updated_at)
            except (ValueError, AttributeError):
                # 파싱 실패 시 None으로 처리
                memo_updated_at = None
        
        # Company가 존재하는 경우에만 복원
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
            company.memo = memo
            company.memo_updated_at = memo_updated_at
            company.save(update_fields=['memo', 'memo_updated_at'])
            restored_count += 1
        except CompanyModel.DoesNotExist:
            # Company가 없으면 복원 불가 (무시)
            continue
    
    return restored_count


def load_passed_companies_json(file_path=None):
    """
    필터 통과 기업 JSON 파일 읽기
    
    Args:
        file_path: JSON 파일 경로 (없으면 기본 경로 사용)
        
    Returns:
        dict: {
            'last_updated': str,
            'companies': [
                {'stock_code': str, 'company_name': str, 'corp_code': str},
                ...
            ]
        }
    """
    from django.conf import settings
    import json
    from pathlib import Path
    
    if file_path is None:
        file_path = settings.BASE_DIR / 'passed_filters_companies.json'
    else:
        file_path = Path(file_path)
    
    if not file_path.exists():
        return {
            'last_updated': None,
            'companies': []
        }
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, IOError) as e:
        # 파일이 손상되었거나 읽을 수 없으면 빈 데이터 반환
        return {
            'last_updated': None,
            'companies': []
        }


def save_passed_companies_json(stock_code, company_name, corp_code, file_path=None):
    """
    필터 통과 기업을 JSON 파일에 추가/업데이트
    
    Args:
        stock_code: 종목코드
        company_name: 기업명
        corp_code: 기업번호
        file_path: JSON 파일 경로 (없으면 기본 경로 사용)
        
    Returns:
        bool: 저장 성공 여부
    """
    from django.conf import settings
    import json
    from pathlib import Path
    from datetime import datetime
    
    if file_path is None:
        file_path = settings.BASE_DIR / 'passed_filters_companies.json'
    else:
        file_path = Path(file_path)
    
    # 기존 데이터 로드
    data = load_passed_companies_json(file_path)
    
    # 중복 체크 (stock_code 기준)
    existing_stock_codes = {c['stock_code'] for c in data.get('companies', [])}
    
    if stock_code in existing_stock_codes:
        # 이미 존재하면 업데이트 (기업명이나 corp_code가 변경되었을 수 있음)
        for company in data['companies']:
            if company['stock_code'] == stock_code:
                company['company_name'] = company_name
                company['corp_code'] = corp_code
                break
    else:
        # 새로 추가
        if 'companies' not in data:
            data['companies'] = []
        data['companies'].append({
            'stock_code': stock_code,
            'company_name': company_name,
            'corp_code': corp_code
        })
    
    # last_updated 업데이트
    data['last_updated'] = datetime.now().isoformat()
    
    # 파일 저장
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False


def migrate_txt_to_json(txt_file_path=None, json_file_path=None):
    """
    기존 txt 파일의 데이터를 JSON 파일로 마이그레이션
    
    Args:
        txt_file_path: 기존 txt 파일 경로 (없으면 기본 경로 사용)
        json_file_path: JSON 파일 경로 (없으면 기본 경로 사용)
        
    Returns:
        int: 마이그레이션된 기업 수
    """
    from django.conf import settings
    from pathlib import Path
    from apps.dart.client import DartClient
    from django.apps import apps as django_apps
    
    if txt_file_path is None:
        txt_file_path = settings.BASE_DIR / 'passed_filters_stock_codes.txt'
    else:
        txt_file_path = Path(txt_file_path)
    
    if json_file_path is None:
        json_file_path = settings.BASE_DIR / 'passed_filters_companies.json'
    else:
        json_file_path = Path(json_file_path)
    
    # txt 파일이 없으면 마이그레이션할 데이터 없음
    if not txt_file_path.exists():
        return 0
    
    # txt 파일 읽기
    stock_codes = []
    with open(txt_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            stock_code = line.strip()
            if stock_code:
                stock_codes.append(stock_code)
    
    if not stock_codes:
        # 빈 파일이면 삭제하고 종료
        txt_file_path.unlink()
        return 0
    
    # 종목코드 → corp_code 변환
    dart_client = DartClient()
    if not dart_client._corp_code_mapping_cache:
        dart_client.load_corp_code_xml()
    
    # DB에서 기업명 조회
    CompanyModel = django_apps.get_model('apps', 'Company')
    migrated_count = 0
    
    for stock_code in stock_codes:
        # 종목코드 → corp_code 변환
        corp_code = dart_client._get_corp_code_by_stock_code(stock_code)
        if not corp_code:
            continue
        
        # DB에서 기업명 조회
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
            company_name = company.company_name or ''
        except CompanyModel.DoesNotExist:
            # DB에 없으면 기업명은 빈 문자열
            company_name = ''
        
        # JSON 파일에 저장
        if save_passed_companies_json(stock_code, company_name, corp_code, json_file_path):
            migrated_count += 1
    
    # 마이그레이션 완료 후 txt 파일 삭제
    if migrated_count > 0:
        txt_file_path.unlink()
    
    return migrated_count

