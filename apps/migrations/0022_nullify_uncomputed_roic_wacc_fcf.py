# Generated 2026-07-01: 미계산 행(roic=0.0 AND wacc=0.0)의 roic·wacc·fcf를 NULL로 정리.
#
# self-contained: 라이브 서비스 함수(apps.service.db.nullify_uncomputed_indicators)를
# import하지 않고 historical 모델(apps.get_model)로 직접 처리한다. 이렇게 해야 미래에
# roic/wacc/fcf 필드가 rename/drop 되어도 fresh migration 재생(테스트DB 빌드 포함)이
# 이 마이그레이션 시점의 스키마로 안전하게 재현된다(라이브 함수는 현재 모델을 잡아 깨질 수 있음).
# 동일 로직의 런타임/테스트용 함수는 db.nullify_uncomputed_indicators에 별도 유지.

from django.db import migrations


def forwards(apps, schema_editor):
    YearlyFinancialData = apps.get_model("apps", "YearlyFinancialData")
    YearlyFinancialData.objects.filter(roic=0.0, wacc=0.0).update(
        roic=None, wacc=None, fcf=None
    )


class Migration(migrations.Migration):

    dependencies = [
        ("apps", "0021_yearlyfinancialdata_altman_z_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
