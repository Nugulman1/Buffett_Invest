"""
KRX 당일 전체 종목 스냅샷 수집 (08:30 스케줄용)

사용법:
    python manage.py fetch_krx_daily

재수집 조건(파일 없음 / bas_dd가 오늘과 다르고 현재 08:30 KST 이상)이면
ensure_latest_snapshot()에서 API 호출 후 JSON 저장.
cron 등으로 08:30 KST에 실행하도록 설정하면 됩니다.
"""
from django.core.management.base import BaseCommand
from apps.service.krx_client import ensure_latest_snapshot, _get_kst_now


class Command(BaseCommand):
    help = "KRX 당일 전체 종목 JSON 스냅샷 수집 (재수집 조건 시에만 API 호출)"

    def handle(self, *args, **options):
        now = _get_kst_now()
        snap = ensure_latest_snapshot()
        if snap:
            self.stdout.write(
                self.style.SUCCESS(
                    f"스냅샷 완료: bas_dd={snap.get('bas_dd')} collected_at={snap.get('collected_at')} "
                    f"rows={len(snap.get('rows') or [])}건 (KST {now.strftime('%Y-%m-%d %H:%M')})"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING("스냅샷 없음 (API 키 없음 또는 재수집 조건 미충족 시 기존 파일도 없음)")
            )
