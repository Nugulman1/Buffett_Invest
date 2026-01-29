"""
금액 포맷팅 (stdlib만 사용)
"""


def format_amount_korean(amount: int) -> str:
    """
    금액을 조, 억, 만 단위로 보기 쉽게 포맷팅

    Args:
        amount: 금액 (정수)

    Returns:
        포맷팅된 문자열 (예: "514조 5,319억 4,800만원")
    """
    if amount == 0:
        return "0원"

    is_negative = amount < 0
    amount = abs(amount)

    cho = amount // 1_000_000_000_000
    eok = (amount % 1_000_000_000_000) // 100_000_000
    man = (amount % 100_000_000) // 10_000
    remainder = amount % 10_000

    parts = []

    if cho > 0:
        parts.append(f"{cho:,}조")
    if eok > 0:
        parts.append(f"{eok:,}억")
    if man > 0:
        parts.append(f"{man:,}만")
    if remainder > 0:
        parts.append(f"{remainder:,}")

    if not parts:
        result = "0원"
    else:
        result = " ".join(parts) + "원"

    if is_negative:
        result = f"-{result}"

    return result
