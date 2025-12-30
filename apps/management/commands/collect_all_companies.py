"""
전체 기업 데이터 수집 관리 명령어

종목코드.md 파일에서 기업 코드를 읽어서 재무 데이터를 수집합니다.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from pathlib import Path
from datetime import datetime, date, timedelta
from apps.service.orchestrator import DataOrchestrator
from apps.dart.client import DartClient
from django.apps import apps as django_apps


class Command(BaseCommand):
    help = '종목코드.md 파일에서 기업 데이터를 수집합니다. (500개 제한)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='수집할 최대 기업 수 (기본값: 10)',
        )
    
    def handle(self, *args, **options):
        limit = options['limit']
        BASE_DIR = Path(__file__).parent.parent.parent.parent
        
        # 파일 경로
        stock_codes_file = BASE_DIR / '종목코드.md'
        collected_file = BASE_DIR / 'collected_stock_codes.txt'
        passed_filters_file = BASE_DIR / 'passed_filters_stock_codes.txt'
        
        # 수집 완료 종목코드 로드
        collected_stock_codes = self.load_collected_stock_codes(collected_file)
        
        # 종목코드.md 파일 파싱
        stock_codes = self.parse_stock_codes_file(stock_codes_file, collected_stock_codes, limit)
        
        if not stock_codes:
            self.stdout.write(self.style.WARNING('수집할 종목코드가 없습니다.'))
            return
        
        self.stdout.write(f'총 {len(stock_codes)}개 종목코드 수집 시작...')
        self.stdout.write(f'이미 수집된 종목코드: {len(collected_stock_codes)}개')
        
        # 초기화
        orchestrator = DataOrchestrator()
        dart_client = DartClient()
        
        # XML 캐시 미리 로드 (한 번만 다운로드)
        self.stdout.write('기업 고유번호 XML 파일 로딩 중...')
        dart_client.load_corp_code_xml()
        self.stdout.write(self.style.SUCCESS(f'XML 로드 완료 (총 {len(dart_client._corp_code_mapping_cache)}개 매핑)'))
        
        # 통계
        success_count = 0
        fail_count = 0
        skip_count = 0
        new_collected = []  # 이번 실행에서 새로 수집한 종목코드
        passed_filter_stock_codes = []  # 필터 통과한 종목코드 (주석 처리)
        
        # 각 종목코드 처리
        for idx, stock_code in enumerate(stock_codes, 1):
            try:
                self.stdout.write(f'[{idx}/{len(stock_codes)}] {stock_code} 처리 중...', ending='')
                
                # 종목코드 → corp_code 변환
                corp_code = dart_client._get_corp_code_by_stock_code(stock_code)
                if not corp_code:
                    self.stdout.write(self.style.WARNING(' → 종목코드 변환 실패'))
                    fail_count += 1
                    continue
                
                # 수집 날짜 기준 확인
                if not self.should_collect_company(corp_code):
                    self.stdout.write(self.style.WARNING(' → 이미 수집됨 (스킵)'))
                    skip_count += 1
                    continue
                
                # 데이터 수집
                company_data = orchestrator.collect_company_data(corp_code)
                
                # 수집 성공
                new_collected.append(stock_code)
                success_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f' → 성공 ({company_data.company_name})'
                    )
                )
                
                # 필터 통과 기업 저장
                if company_data.passed_all_filters:
                    passed_filter_stock_codes.append(stock_code)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'   [필터 통과] {stock_code} ({company_data.company_name})'
                        )
                    )
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f' → 에러: {str(e)}'))
                fail_count += 1
                import traceback
                traceback.print_exc()
        
        # 수집 완료된 종목코드를 파일에 추가
        if new_collected:
            self.save_collected_stock_codes(collected_file, new_collected)
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n수집 완료된 종목코드 {len(new_collected)}개 저장: {collected_file}'
                )
            )
        
        # 필터 통과 기업 저장
        if passed_filter_stock_codes:
            # 기존 파일 로드 (중복 방지)
            existing_passed = set()
            if passed_filters_file.exists():
                with open(passed_filters_file, 'r', encoding='utf-8') as f:
                    existing_passed = set(line.strip() for line in f if line.strip())
            
            # 새로 통과한 것만 추가 (중복 제거)
            new_passed = [
                code for code in passed_filter_stock_codes 
                if code not in existing_passed
            ]
            
            if new_passed:
                # 파일에 추가 (append 모드)
                with open(passed_filters_file, 'a', encoding='utf-8') as f:
                    for stock_code in new_passed:
                        f.write(f"{stock_code}\n")
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'필터 통과 기업 {len(new_passed)}개 저장 완료: {passed_filters_file}'
                    )
                )
        
        # 최종 결과 출력
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS(f'수집 완료!'))
        self.stdout.write(f'  성공: {success_count}개')
        self.stdout.write(f'  실패: {fail_count}개')
        self.stdout.write(f'  스킵: {skip_count}개')
        self.stdout.write(f'  필터 통과: {len(passed_filter_stock_codes)}개')
        self.stdout.write(f'  총계: {success_count + fail_count + skip_count}개')
        self.stdout.write('=' * 60)
    
    def load_collected_stock_codes(self, collected_file: Path) -> set:
        """수집 완료된 종목코드 로드"""
        if collected_file.exists():
            with open(collected_file, 'r', encoding='utf-8') as f:
                return set(line.strip() for line in f if line.strip())
        return set()
    
    def parse_stock_codes_file(self, stock_codes_file: Path, collected_stock_codes: set, limit: int) -> list:
        """종목코드.md 파일 파싱"""
        if not stock_codes_file.exists():
            self.stdout.write(self.style.ERROR(f'파일을 찾을 수 없습니다: {stock_codes_file}'))
            return []
        
        stock_codes = []
        with open(stock_codes_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            # 첫 줄 "종목코드" 헤더 제외
            for line in lines[1:]:
                stock_code = line.strip()
                # 빈 줄 제외, 이미 수집된 것 제외
                if stock_code and stock_code not in collected_stock_codes:
                    stock_codes.append(stock_code)
                    if len(stock_codes) >= limit:
                        break
        
        return stock_codes
    
    def should_collect_company(self, corp_code: str) -> bool:
        """
        기업 수집 필요 여부 확인 (4월 1일 기준)
        
        - DB에 기업이 없으면 수집
        - last_collected_at이 없으면 수집
        - 4월 1일 기준으로 1년이 지났으면 수집
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
    
    def save_collected_stock_codes(self, collected_file: Path, new_stock_codes: list):
        """수집 완료된 종목코드를 파일에 추가"""
        with open(collected_file, 'a', encoding='utf-8') as f:
            for stock_code in new_stock_codes:
                f.write(f"{stock_code}\n")

