"""
(Deprecated) 필터 통과 목록은 이제 DB(Company.passed_all_filters, passed_second_filter)만 사용합니다.
이 명령은 더 이상 사용되지 않습니다.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Deprecated: 필터 통과 목록은 DB만 사용합니다. 이 명령은 더 이상 동작하지 않습니다.'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                '필터 통과 기업 목록은 JSON이 아닌 DB(Company)에서 조회합니다. '
                '이 마이그레이션 명령은 더 이상 필요하지 않습니다.'
            )
        )
