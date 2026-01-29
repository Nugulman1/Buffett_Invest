"""
ACODE 정규화 유틸 (XBRL 전용)
"""


def normalize_acode(acode: str) -> str:
    """
    ACODE 정규화 함수

    XBRL ACODE 매칭을 위한 전처리:
    - 콜론(:)을 언더스코어(_)로 변환
    - 영어 소문자 변환

    Args:
        acode: 원본 ACODE (예: "ifrs-full:CurrentPortionOfLongTermBorrowings")

    Returns:
        정규화된 ACODE (예: "ifrs-full_currentportionoflongtermborrowings")
    """
    if not acode:
        return ""

    normalized = acode.replace(":", "_")
    normalized = normalized.lower()
    return normalized
