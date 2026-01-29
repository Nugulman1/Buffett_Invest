"""
기업 메모 백업/복원 (Company 모델 + dict/list)
"""
from datetime import datetime

from django.apps import apps as django_apps
from django.utils import timezone


def backup_company_memos(corp_code: str = None) -> dict | list | None:
    """
    기업 메모 백업

    Args:
        corp_code: 고유번호 (None이면 전체 기업)

    Returns:
        단일 기업: {'corp_code': '...', 'memo': '...', 'memo_updated_at': '...'} 또는 None (메모 없음)
        전체 기업: [{'corp_code': '...', 'memo': '...', 'memo_updated_at': '...'}, ...]
    """
    CompanyModel = django_apps.get_model('apps', 'Company')

    if corp_code:
        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
            if company.memo:
                return {
                    'corp_code': company.corp_code,
                    'memo': company.memo,
                    'memo_updated_at': company.memo_updated_at.isoformat() if company.memo_updated_at else None
                }
            return None
        except CompanyModel.DoesNotExist:
            return None
    else:
        memos = []
        for company in CompanyModel.objects.exclude(memo__isnull=True).exclude(memo=''):
            memos.append({
                'corp_code': company.corp_code,
                'memo': company.memo,
                'memo_updated_at': company.memo_updated_at.isoformat() if company.memo_updated_at else None
            })
        return memos


def restore_company_memos(memo_backup: dict | list) -> int:
    """
    기업 메모 복원

    Args:
        memo_backup: backup_company_memos()로 백업한 데이터
        - 단일 기업: {'corp_code': '...', 'memo': '...', 'memo_updated_at': '...'}
        - 전체 기업: [{'corp_code': '...', 'memo': '...', 'memo_updated_at': '...'}, ...]

    Returns:
        복원된 메모 개수
    """
    CompanyModel = django_apps.get_model('apps', 'Company')
    restored_count = 0
    memos_to_restore = [memo_backup] if isinstance(memo_backup, dict) else memo_backup

    for memo_data in memos_to_restore:
        if not memo_data or 'corp_code' not in memo_data:
            continue

        corp_code = memo_data['corp_code']
        memo = memo_data.get('memo', '')
        memo_updated_at_str = memo_data.get('memo_updated_at')

        memo_updated_at = None
        if memo_updated_at_str:
            try:
                memo_updated_at = datetime.fromisoformat(memo_updated_at_str.replace('Z', '+00:00'))
                if memo_updated_at.tzinfo is None:
                    memo_updated_at = timezone.make_aware(memo_updated_at)
            except (ValueError, AttributeError):
                memo_updated_at = None

        try:
            company = CompanyModel.objects.get(corp_code=corp_code)
            company.memo = memo
            company.memo_updated_at = memo_updated_at
            company.save(update_fields=['memo', 'memo_updated_at'])
            restored_count += 1
        except CompanyModel.DoesNotExist:
            continue

    return restored_count
