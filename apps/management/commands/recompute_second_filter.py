"""
2차 필터(passed_second_filter) 재계산 관리 명령어.

roic/wacc 데이터가 바뀐 뒤(예: 마이그레이션 0022가 미계산 행을 None으로 정리),
저장된 Company.passed_second_filter가 현재 check_second_filter() 결과와 어긋날 수 있다.
이 명령은 **이미 2차 평가된 회사(passed_second_filter IS NOT NULL)만** 순회하며
플래그를 현재 로직으로 재계산해 일치시킨다. 미평가(None) 회사는 절대 건드리지 않는다
(None→False로 의미가 바뀌는 것을 방지).

사용법:
    python manage.py recompute_second_filter
"""
from django.core.management.base import BaseCommand
from django.apps import apps as django_apps

from apps.service.filter import CompanyFilter
from apps.service.db import update_second_filter_result


class Command(BaseCommand):
    help = (
        '이미 2차 평가된 회사의 passed_second_filter를 현재 roic/wacc로 재계산해 '
        '저장값과 일치시킵니다. 미평가(None) 회사는 제외합니다.'
    )

    def handle(self, *args, **options):
        CompanyModel = django_apps.get_model('apps', 'Company')

        evaluated = CompanyModel.objects.exclude(
            passed_second_filter__isnull=True
        ).values_list('corp_code', 'passed_second_filter')

        scanned = 0
        changed = 0
        for corp_code, stored in evaluated.iterator():
            scanned += 1
            current = CompanyFilter.check_second_filter(corp_code)
            if current != stored:
                update_second_filter_result(corp_code)
                changed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'[OK] 2차 필터 재계산 완료: 평가된 {scanned}개 회사 중 '
                f'{changed}개의 passed_second_filter를 교정했습니다.'
            )
        )
