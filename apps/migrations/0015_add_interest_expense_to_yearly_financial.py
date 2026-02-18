# Generated migration for interest_expense (이자비용, WACC 등 재활용)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('apps', '0014_add_dividend_payout_ratio'),
    ]

    operations = [
        migrations.AddField(
            model_name='yearlyfinancialdata',
            name='interest_expense',
            field=models.BigIntegerField(blank=True, null=True, verbose_name='이자비용'),
        ),
    ]
