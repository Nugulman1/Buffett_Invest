"""
재무지표 데이터 삭제 관리 명령어

사용법:
    python manage.py clear_financial_data                    # 전체 기업 재무지표 삭제
    python manage.py clear_financial_data --corp-code 00126380  # 특정 기업만 삭제
"""
from pathlib import Path
from django.core.management.base import BaseCommand
from django.apps import apps as django_apps
from django.db import transaction


class Command(BaseCommand):
    help = '재무지표 데이터(YearlyFinancialData)만 삭제하고 Company는 유지합니다. (메모 보존)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--corp-code',
            type=str,
            default=None,
            help='특정 기업의 고유번호 (8자리). 지정하지 않으면 전체 기업의 재무지표 삭제',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='확인 없이 바로 실행 (주의: 데이터 삭제)',
        )

    def handle(self, *args, **options):
        CompanyModel = django_apps.get_model('apps', 'Company')
        YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')
        
        corp_code = options.get('corp_code')
        confirm = options.get('confirm', False)
        
        if corp_code:
            # 특정 기업만 삭제
            try:
                company = CompanyModel.objects.get(corp_code=corp_code)
                yearly_data_count = YearlyFinancialDataModel.objects.filter(company=company).count()
                
                if yearly_data_count == 0:
                    self.stdout.write(
                        self.style.WARNING(f'기업 {company.company_name} ({corp_code})의 재무지표 데이터가 없습니다.')
                    )
                    return
                
                if not confirm:
                    self.stdout.write(
                        self.style.WARNING(
                            f'\n경고: 기업 {company.company_name} ({corp_code})의 재무지표 데이터 {yearly_data_count}개를 삭제합니다.\n'
                            f'Company 정보와 메모는 유지되지만, 필터 필드는 초기화됩니다.\n'
                            f'계속하려면 --confirm 옵션을 추가하세요.'
                        )
                    )
                    return
                
                with transaction.atomic():
                    # YearlyFinancialData 삭제
                    deleted_count = YearlyFinancialDataModel.objects.filter(company=company).delete()[0]
                    # last_collected_at 초기화 (재수집 가능하게)
                    company.last_collected_at = None
                    # 필터 관련 필드 초기화
                    company.passed_all_filters = False
                    company.filter_operating_income = False
                    company.filter_net_income = False
                    company.filter_revenue_cagr = False
                    company.filter_operating_margin = False
                    company.filter_roe = False
                    company.save(update_fields=[
                        'last_collected_at',
                        'passed_all_filters',
                        'filter_operating_income',
                        'filter_net_income',
                        'filter_revenue_cagr',
                        'filter_operating_margin',
                        'filter_roe'
                    ])
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ 기업 {company.company_name} ({corp_code})의 재무지표 데이터 {deleted_count}개를 삭제했습니다.\n'
                        f'  메모는 보존되었습니다. (last_collected_at 및 필터 필드 초기화됨)'
                    )
                )
                
            except CompanyModel.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'기업을 찾을 수 없습니다: {corp_code}')
                )
        else:
            # 전체 기업 재무지표 삭제
            total_companies = CompanyModel.objects.count()
            total_yearly_data = YearlyFinancialDataModel.objects.count()
            
            if total_yearly_data == 0:
                self.stdout.write(
                    self.style.WARNING('삭제할 재무지표 데이터가 없습니다.')
                )
                return
            
            if not confirm:
                self.stdout.write(
                    self.style.WARNING(
                        f'\n경고: 전체 {total_companies}개 기업의 재무지표 데이터 {total_yearly_data}개를 삭제합니다.\n'
                        f'Company 정보와 메모는 모두 유지되지만, 필터 필드는 초기화됩니다.\n'
                        f'passed_filters_stock_codes.txt 파일도 초기화됩니다.\n'
                        f'계속하려면 --confirm 옵션을 추가하세요.'
                    )
                )
                return
            
            with transaction.atomic():
                # 전체 YearlyFinancialData 삭제
                deleted_count = YearlyFinancialDataModel.objects.all().delete()[0]
                # 모든 Company의 last_collected_at 및 필터 필드 초기화
                CompanyModel.objects.all().update(
                    last_collected_at=None,
                    passed_all_filters=False,
                    filter_operating_income=False,
                    filter_net_income=False,
                    filter_revenue_cagr=False,
                    filter_operating_margin=False,
                    filter_roe=False
                )
            
            # passed_filters_stock_codes.txt 파일 초기화 (전체 재수집 시)
            passed_filters_file = Path(__file__).resolve().parent.parent.parent.parent / 'passed_filters_stock_codes.txt'
            if passed_filters_file.exists():
                passed_filters_file.write_text('', encoding='utf-8')
                self.stdout.write(
                    self.style.SUCCESS(f'✓ 필터 통과 기업 목록 파일 초기화: {passed_filters_file.name}')
                )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ 전체 {total_companies}개 기업의 재무지표 데이터 {deleted_count}개를 삭제했습니다.\n'
                    f'  모든 메모는 보존되었습니다. (last_collected_at 및 필터 필드 초기화됨)'
                )
            )
