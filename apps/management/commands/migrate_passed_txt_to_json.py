"""
기존 txt 파일의 필터 통과 기업 데이터를 JSON 파일로 마이그레이션

사용법:
    python manage.py migrate_passed_txt_to_json
    python manage.py migrate_passed_txt_to_json --txt-path path/to/file.txt --json-path path/to/file.json
"""
from pathlib import Path

from django.conf import settings
from django.apps import apps as django_apps
from django.core.management.base import BaseCommand

from apps.dart.client import DartClient
from apps.service.passed_json import save_passed_companies_json


class Command(BaseCommand):
    help = '기존 passed_filters_stock_codes.txt 데이터를 passed_filters_companies.json으로 마이그레이션합니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--txt-path',
            type=str,
            default=None,
            help='기존 txt 파일 경로 (기본: BASE_DIR/passed_filters_stock_codes.txt)',
        )
        parser.add_argument(
            '--json-path',
            type=str,
            default=None,
            help='JSON 파일 경로 (기본: BASE_DIR/passed_filters_companies.json)',
        )

    def handle(self, *args, **options):
        txt_file_path = options.get('txt_path')
        json_file_path = options.get('json_path')

        if txt_file_path is None:
            txt_file_path = settings.BASE_DIR / 'passed_filters_stock_codes.txt'
        else:
            txt_file_path = Path(txt_file_path)

        if json_file_path is None:
            json_file_path = settings.BASE_DIR / 'passed_filters_companies.json'
        else:
            json_file_path = Path(json_file_path)

        if not txt_file_path.exists():
            self.stdout.write(self.style.WARNING('txt 파일이 없습니다. 마이그레이션할 데이터가 없습니다.'))
            return

        stock_codes = []
        with open(txt_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                stock_code = line.strip()
                if stock_code:
                    stock_codes.append(stock_code)

        if not stock_codes:
            txt_file_path.unlink()
            self.stdout.write('빈 txt 파일을 삭제했습니다.')
            return

        dart_client = DartClient()
        if not dart_client._corp_code_mapping_cache:
            dart_client.load_corp_code_xml()

        CompanyModel = django_apps.get_model('apps', 'Company')
        migrated_count = 0

        for stock_code in stock_codes:
            corp_code = dart_client._get_corp_code_by_stock_code(stock_code)
            if not corp_code:
                continue

            try:
                company = CompanyModel.objects.get(corp_code=corp_code)
                company_name = company.company_name or ''
            except CompanyModel.DoesNotExist:
                company_name = ''

            if save_passed_companies_json(stock_code, company_name, corp_code, json_file_path):
                migrated_count += 1

        if migrated_count > 0:
            txt_file_path.unlink()

        self.stdout.write(self.style.SUCCESS(f'마이그레이션 완료: {migrated_count}건'))
