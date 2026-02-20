# KRX 일별 데이터는 JSON 스냅샷만 사용 (KrxDailyData 테이블 제거)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("apps", "0018_add_selling_admin_expense_ratio"),
    ]

    operations = [
        migrations.DeleteModel(name="KrxDailyData"),
    ]
