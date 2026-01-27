"""
메모 데이터 복원 관리 명령어

사용법:
    python manage.py restore_memos memos_backup.json
"""
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.apps import apps as django_apps
from django.utils import timezone
from datetime import datetime


class Command(BaseCommand):
    help = '백업된 메모 데이터를 복원합니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            'backup_file',
            type=str,
            help='백업 파일 경로 (JSON)',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='확인 없이 바로 실행',
        )

    def handle(self, *args, **options):
        backup_file = Path(options['backup_file'])
        confirm = options.get('confirm', False)
        
        if not backup_file.exists():
            self.stdout.write(
                self.style.ERROR(f'백업 파일을 찾을 수 없습니다: {backup_file}')
            )
            return
        
        # JSON 파일 읽기
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                memos = json.load(f)
        except json.JSONDecodeError as e:
            self.stdout.write(
                self.style.ERROR(f'JSON 파일 파싱 오류: {e}')
            )
            return
        
        if not memos:
            self.stdout.write(
                self.style.WARNING('백업 파일에 메모 데이터가 없습니다.')
            )
            return
        
        # 리스트로 변환 (단일 객체인 경우)
        if isinstance(memos, dict):
            memos = [memos]
        
        if not confirm:
            self.stdout.write(
                self.style.WARNING(
                    f'\n경고: {len(memos)}개 기업의 메모를 복원합니다.\n'
                    f'기존 메모는 덮어씌워집니다.\n'
                    f'계속하려면 --confirm 옵션을 추가하세요.'
                )
            )
            return
        
        CompanyModel = django_apps.get_model('apps', 'Company')
        restored_count = 0
        not_found_count = 0
        
        for memo_data in memos:
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
                    memo_updated_at = None
            
            # Company가 존재하는 경우에만 복원
            try:
                company = CompanyModel.objects.get(corp_code=corp_code)
                company.memo = memo
                company.memo_updated_at = memo_updated_at
                company.save(update_fields=['memo', 'memo_updated_at'])
                restored_count += 1
            except CompanyModel.DoesNotExist:
                not_found_count += 1
                company_name = memo_data.get('company_name', '알 수 없음')
                self.stdout.write(
                    self.style.WARNING(f'  ⚠ 기업을 찾을 수 없음: {company_name} ({corp_code})')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ 메모 복원 완료:\n'
                f'  복원됨: {restored_count}개\n'
                f'  찾을 수 없음: {not_found_count}개'
            )
        )
