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


def internal_yuan_from_display_rice_g(rice_g: int) -> Decimal:
    """Inverse of rice_grams_from_internal for admin/test wallet tweaks."""
    pay = Decimal(int(rice_g)) / Decimal(str(settings.rice_grams_per_yuan))
    return (pay * _ratio()).quantize(Decimal("0.0001"))


def charged_pay_yuan_from_usd(usd_cost: float) -> Decimal:
    """User-facing CNY charge for a USD model cost (× display multiplier only)."""
    usd = Decimal(str(max(0.0, float(usd_cost))))
    cny = (usd * Decimal(str(settings.usd_cny_rate))).quantize(Decimal("0.0000001"))
    mult = Decimal(str(settings.usage_display_multiplier))
    return (cny * mult).quantize(Decimal("0.0000001"))


def display_rice_grams_from_usd(usd_cost: float) -> int:
    """User-visible 白饭：真实模型 USD 成本 → CNY → × 展示倍数 → 克。

    Formula: usd × usd_cny_rate × usage_display_multiplier × rice_grams_per_yuan.
    Topup credit ratio is NOT applied here — markup is only the display multiplier.
    """
    return pay_yuan_to_rice_grams(charged_pay_yuan_from_usd(usd_cost))


def internal_yuan_from_usd_charge(usd_cost: float) -> Decimal:
    """Ledger debit so bowl rice drops by the same grams as display_rice_grams_from_usd.

    Wallet stores internal yuan (topup × ratio). Display rice = internal ÷ ratio × 500g,
    so debit = charged_pay_yuan × ratio.
    """
    return (charged_pay_yuan_from_usd(usd_cost) * _ratio()).quantize(Decimal("0.0001"))
