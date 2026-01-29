"""
기업 규모 분류 (stdlib만 사용)
"""


def classify_company_size(total_assets: int) -> str:
    """
    총자산 기준으로 기업 규모 분류

    분류 기준:
    - 중소기업: 총자산 < 5천억원 (5,000,000,000)
    - 대기업: 총자산 ≥ 10조원 (10,000,000,000,000)
    - 중견기업: 그 외 (5천억원 이상 10조원 미만)

    Args:
        total_assets: 총자산 (정수, 원 단위)

    Returns:
        기업 규모 ('small', 'medium', 'large')
    """
    SMALL_THRESHOLD = 5_000_000_000
    LARGE_THRESHOLD = 10_000_000_000_000

    if total_assets < SMALL_THRESHOLD:
        return 'small'
    elif total_assets >= LARGE_THRESHOLD:
        return 'large'
    else:
        return 'medium'
