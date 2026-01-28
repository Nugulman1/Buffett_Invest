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
from django.conf import settings


class Command(BaseCommand):
    help = '재무지표 데이터의 기본 필드만 초기화하고 FCF, ROIC, WACC는 보존합니다. (메모 보존)'

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
        QuarterlyFinancialDataModel = django_apps.get_model('apps', 'QuarterlyFinancialData')
        
        corp_code = options.get('corp_code')
        confirm = options.get('confirm', False)
        
        if corp_code:
            # 특정 기업만 삭제
            try:
                company = CompanyModel.objects.get(corp_code=corp_code)
                yearly_data_count = YearlyFinancialDataModel.objects.filter(company=company).count()
                quarterly_data_count = QuarterlyFinancialDataModel.objects.filter(company=company).count()
                
                if yearly_data_count == 0 and quarterly_data_count == 0:
                    self.stdout.write(
                        self.style.WARNING(f'기업 {company.company_name} ({corp_code})의 재무지표 데이터가 없습니다.')
                    )
                    return
                
                if not confirm:
                    self.stdout.write(
                        self.style.WARNING(
                            f'\n경고: 기업 {company.company_name} ({corp_code})의 재무지표 기본 필드를 초기화합니다.\n'
                            f'연도별 데이터 기본 필드 초기화 및 분기 데이터 {quarterly_data_count}개 삭제.\n'
                            f'FCF, ROIC, WACC는 보존되며, Company 정보와 메모도 유지됩니다.\n'
                            f'필터 필드는 초기화됩니다.\n'
                            f'계속하려면 --confirm 옵션을 추가하세요.'
                        )
                    )
                    return
                
                with transaction.atomic():
                    # YearlyFinancialData의 기본 필드만 초기화 (FCF, ROIC, WACC는 보존)
                    updated_count = YearlyFinancialDataModel.objects.filter(company=company).update(
                        revenue=0,
                        operating_income=0,
                        net_income=0,
                        total_assets=0,
                        total_equity=0,
                        operating_margin=0.0,
                        roe=0.0,
                        # fcf, roic, wacc는 업데이트하지 않음 (보존)
                    )
                    # 분기 데이터 삭제
                    deleted_quarterly_count = QuarterlyFinancialDataModel.objects.filter(company=company).delete()[0]
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
                        f'✓ 기업 {company.company_name} ({corp_code})의 재무지표 기본 필드 {updated_count}개를 초기화하고 분기 데이터 {deleted_quarterly_count}개를 삭제했습니다.\n'
                        f'  FCF, ROIC, WACC는 보존되었으며, 메모도 보존되었습니다. (last_collected_at 및 필터 필드 초기화됨)'
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
            total_quarterly_data = QuarterlyFinancialDataModel.objects.count()
            
            if total_yearly_data == 0 and total_quarterly_data == 0:
                self.stdout.write(
                    self.style.WARNING('삭제할 재무지표 데이터가 없습니다.')
                )
                return
            
            if not confirm:
                self.stdout.write(
                    self.style.WARNING(
                        f'\n경고: 전체 {total_companies}개 기업의 재무지표 기본 필드를 초기화합니다.\n'
                        f'연도별 데이터 기본 필드 초기화 및 분기 데이터 {total_quarterly_data}개 삭제.\n'
                        f'FCF, ROIC, WACC는 보존되며, Company 정보와 메모도 모두 유지됩니다.\n'
                        f'필터 필드는 초기화됩니다.\n'
                        f'passed_filters_companies.json 파일도 초기화됩니다.\n'
                        f'계속하려면 --confirm 옵션을 추가하세요.'
                    )
                )
                return
            
            with transaction.atomic():
                # 전체 YearlyFinancialData의 기본 필드만 초기화 (FCF, ROIC, WACC는 보존)
                updated_count = YearlyFinancialDataModel.objects.all().update(
                    revenue=0,
                    operating_income=0,
                    net_income=0,
                    total_assets=0,
                    total_equity=0,
                    operating_margin=0.0,
                    roe=0.0,
                    # fcf, roic, wacc는 업데이트하지 않음 (보존)
                )
                # 전체 분기 데이터 삭제
                deleted_quarterly_count = QuarterlyFinancialDataModel.objects.all().delete()[0]
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
            
            # passed_filters_companies.json 파일 초기화 (전체 재수집 시)
            import json
            passed_filters_file = settings.BASE_DIR / 'passed_filters_companies.json'
            if passed_filters_file.exists():
                # JSON 파일을 빈 구조로 초기화
                empty_data = {
                    'last_updated': None,
                    'companies': []
                }
                with open(passed_filters_file, 'w', encoding='utf-8') as f:
                    json.dump(empty_data, f, ensure_ascii=False, indent=2)
                self.stdout.write(
                    self.style.SUCCESS(f'✓ 필터 통과 기업 목록 파일 초기화: {passed_filters_file.name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'필터 통과 기업 목록 파일이 없습니다: {passed_filters_file}')
                )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ 전체 {total_companies}개 기업의 재무지표 기본 필드 {updated_count}개를 초기화하고 분기 데이터 {deleted_quarterly_count}개를 삭제했습니다.\n'
                    f'  FCF, ROIC, WACC는 보존되었으며, 모든 메모도 보존되었습니다. (last_collected_at 및 필터 필드 초기화됨)'
                )
            )
