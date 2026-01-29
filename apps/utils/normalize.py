"""
계정명 정규화 (stdlib만 사용)
"""


def normalize_account_name(account_name: str) -> str:
    """
    계정명 정규화 함수

    계정명 매칭을 위한 전처리:
    - 공백 제거
    - 괄호 정리 (중복 괄호 처리 등)
    - 영어 소문자 변환

    Args:
        account_name: 원본 계정명

    Returns:
        정규화된 계정명
    """
    if not account_name:
        return ""

    normalized = account_name.strip()
    normalized = normalized.replace(" (", "(").replace(") ", ")")
    normalized = normalized.lower()

    return normalized
