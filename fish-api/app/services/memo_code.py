import secrets
from decimal import Decimal

# First 3 digits = integer yuan (001–999); last 4 hex chars = random order id.
MEMO_AMOUNT_WIDTH = 3
MEMO_RANDOM_HEX_LEN = 4
MEMO_MAX_YUAN = 10**MEMO_AMOUNT_WIDTH - 1


def build_memo_code(amount_yuan: int) -> str:
    """Build Alipay transfer memo: amount prefix + random suffix.

    Args:
        amount_yuan: Whole-number top-up amount in CNY.

    Returns:
        Memo string, e.g. ``002A3F9`` for ¥2.

    Raises:
        ValueError: If amount is out of supported range.
    """
    if amount_yuan < 1 or amount_yuan > MEMO_MAX_YUAN:
        msg = f"amount_yuan must be 1..{MEMO_MAX_YUAN}"
        raise ValueError(msg)
    prefix = f"{amount_yuan:0{MEMO_AMOUNT_WIDTH}d}"
    suffix = secrets.token_hex(MEMO_RANDOM_HEX_LEN // 2).upper()
    return f"{prefix}{suffix}"


def parse_memo_amount_yuan(memo_code: str) -> int | None:
    """Read the encoded yuan amount from the memo prefix.

    Args:
        memo_code: Transfer memo shown to customer and operator.

    Returns:
        Integer yuan, or None if prefix is not numeric.
    """
    if len(memo_code) < MEMO_AMOUNT_WIDTH:
        return None
    prefix = memo_code[:MEMO_AMOUNT_WIDTH]
    if not prefix.isdigit():
        return None
    return int(prefix, 10)


def require_integer_yuan(amount: Decimal) -> int:
    """Normalize order amount to whole yuan.

    Args:
        amount: Requested top-up amount.

    Returns:
        Integer yuan.

    Raises:
        ValueError: If amount is not a whole number of yuan.
    """
    quantized = amount.quantize(Decimal("0.01"))
    if quantized != quantized.to_integral_value():
        raise ValueError("integer_yuan_only")
    yuan = int(quantized)
    if yuan < 1:
        raise ValueError("amount_too_small")
    return yuan
