"""
메모 데이터 백업 관리 명령어

사용법:
    python manage.py backup_memos
    python manage.py backup_memos --output my_backup.json
"""
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.apps import apps as django_apps


class Command(BaseCommand):
    help = '기업 메모 데이터를 JSON 파일로 백업합니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='memos_backup.json',
            help='백업 파일 경로 (기본값: memos_backup.json)',
        )

    def handle(self, *args, **options):
        CompanyModel = django_apps.get_model('apps', 'Company')
        
        # 메모가 있는 기업만 백업
        memos = []
        for company in CompanyModel.objects.exclude(memo__isnull=True).exclude(memo=''):
            memos.append({
                'corp_code': company.corp_code,
                'company_name': company.company_name,
                'memo': company.memo,
                'memo_updated_at': company.memo_updated_at.isoformat() if company.memo_updated_at else None
            })
        
        # 백업 파일 경로
        output_path = Path(options['output'])
        
        # JSON 파일로 저장
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(memos, f, ensure_ascii=False, indent=2)
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ 메모 {len(memos)}개를 {output_path}에 백업했습니다.')
        )
