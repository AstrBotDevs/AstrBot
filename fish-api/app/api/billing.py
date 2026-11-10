from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/public-config")
def public_billing_config() -> dict:
    """Public billing rules shown in fish-console (no auth)."""
    return {
        "min_yuan": settings.min_topup_yuan,
        "rice_grams_per_yuan": settings.rice_grams_per_yuan,
        "feed_plans": settings.feed_plans_public(),
        "payment": {
            "alipay_qr_url": settings.alipay_qr_url,
            "pay_hint": settings.alipay_pay_hint,
        },
    }
