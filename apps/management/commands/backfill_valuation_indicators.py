"""
내재가치 5선 지표 백필 관리 명령어

DB에 이미 저장된 입력값(roic·net_income·dividend_paid·total_assets·total_liabilities·
total_equity·current_assets·current_liabilities·retained_earnings·operating_income)만으로
5선 지표(sustainable_growth·altman_z·altman_z_class·zmijewski·zmijewski_flag)를 재계산해
저장한다. DART 재수집 없음.

★데이터 파괴 방지: load_company_from_db→save_company_to_db round-trip을 쓰지 않는다.
load_company_from_db가 current_assets 등 입력을 객체로 안 읽어오는데 save_company_to_db는
그 필드를 getattr(...,None)으로 덮어쓰므로 DB 입력값이 None으로 파괴된다. 대신
YearlyFinancialData 모델 행을 직접 순회하고 5개 필드만 update_fields로 저장한다.

사용법:
    python manage.py backfill_valuation_indicators
"""
from django.core.management.base import BaseCommand
from django.apps import apps as django_apps
from django.db import transaction

from apps.service.calculator import IndicatorCalculator
from apps.service.db import run_with_write_lock_retry

_UPDATE_FIELDS = [
    'sustainable_growth',
    'altman_z',
    'altman_z_class',
    'zmijewski',
    'zmijewski_flag',
]


class Command(BaseCommand):
    help = (
        'DB에 저장된 입력으로 내재가치 5선 지표(g·Z\'\'·등급·Zmijewski·경보)를 재계산해 '
        '해당 5개 필드만 저장합니다. DART 재수집은 하지 않습니다.'
    )

    def handle(self, *args, **options):
        YearlyFinancialDataModel = django_apps.get_model('apps', 'YearlyFinancialData')

        rows = list(YearlyFinancialDataModel.objects.all())
        total_rows = len(rows)

        if total_rows == 0:
            self.stdout.write(self.style.WARNING('백필할 YearlyFinancialData 행이 없습니다.'))
            return

        def _do():
            with transaction.atomic():
                for row in rows:
                    # 모델 행 인스턴스에 직접 5선 지표를 in-place 세팅(다른 입력 필드 불변)
                    IndicatorCalculator.fill_valuation_indicators(row)
                    # 5개 필드만 갱신 — 입력 필드는 절대 안 건드린다
                    row.save(update_fields=_UPDATE_FIELDS)

        run_with_write_lock_retry(_do)

        company_count = (
            YearlyFinancialDataModel.objects.values('company_id').distinct().count()
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'[OK] 내재가치 5선 지표 백필 완료: {company_count}개 기업, '
                f'{total_rows}개 연간 행의 5개 필드를 재계산·저장했습니다.'
            )
        )
