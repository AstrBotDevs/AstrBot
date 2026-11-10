"""白饭：用户可见游戏币；后台仍以内部 APIKEY 元记账。"""

from decimal import Decimal

from app.core.config import settings


def _ratio() -> Decimal:
    ratio = Decimal(str(settings.topup_credit_ratio))
    return ratio if ratio > 0 else Decimal("1")


def alipay_yuan_from_internal(internal_yuan: Decimal) -> Decimal:
    """Map internal APIKEY yuan to 支付宝实付等价元（internal ÷ ratio）。"""
    return (internal_yuan / _ratio()).quantize(Decimal("0.0001"))


def pay_yuan_to_rice_grams(pay_yuan: Decimal) -> int:
    """1 支付宝实付元 = rice_grams_per_yuan 克白饭（默认 1 元 = 500g）。"""
    grams = pay_yuan * Decimal(str(settings.rice_grams_per_yuan))
    return int(grams.to_integral_value())


def rice_grams_from_internal(internal_yuan: Decimal) -> int:
    """内部余额 → 用户白饭：先还原实付等价，再 × 白饭系数。"""
    return pay_yuan_to_rice_grams(alipay_yuan_from_internal(internal_yuan))


def internal_yuan_from_tokens(raw_tokens: int) -> Decimal:
    """Estimate internal yuan cost from token count (until per-model cost is wired)."""
    per_m = Decimal(str(settings.internal_yuan_per_million_tokens))
    return (Decimal(raw_tokens) / Decimal(1_000_000) * per_m).quantize(
        Decimal("0.0001")
    )


def display_rice_grams_from_tokens(raw_tokens: int) -> int:
    """User-visible 白饭消耗：内部元 → 实付等价 × 展示倍数 → 克。"""
    internal = internal_yuan_from_tokens(raw_tokens)
    pay_equiv = alipay_yuan_from_internal(internal)
    mult = Decimal(str(settings.usage_display_multiplier))
    charged_pay = (pay_equiv * mult).quantize(Decimal("0.0001"))
    return pay_yuan_to_rice_grams(charged_pay)
