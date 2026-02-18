# Generated migration for dividend_payout_ratio (FCF 대비 배당성향, 연간)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('apps', '0013_add_krx_daily_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='yearlyfinancialdata',
            name='dividend_payout_ratio',
            field=models.FloatField(blank=True, null=True, verbose_name='배당성향(FCF대비)'),
        ),
    ]
