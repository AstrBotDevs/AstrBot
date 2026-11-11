from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class PaymentPublicConfig(BaseModel):
    alipay_qr_url: str = ""
    pay_hint: str = ""


class WalletPublic(BaseModel):
    """Customer wallet: internal yuan + 白饭（1 实付元=500g；前端主展示 rice_g）。"""

    balance_yuan: Decimal
    balance_rice_g: int
    arrears_yuan: Decimal
    arrears_rice_g: int
    status: str
    can_bind: bool


class CreateOrderRequest(BaseModel):
    amount_yuan: Decimal = Field(gt=0)
    plan_id: str | None = None


class OrderPublic(BaseModel):
    id: str
    amount_yuan: Decimal
    status: str
    pay_channel: str
    memo_code: str
    plan_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminOrderPublic(OrderPublic):
    """Order row for the fish-console admin desk."""

    user_email: str
    credit_yuan: Decimal


class AdminWalletAdjustRequest(BaseModel):
    """Admin-only wallet tweak for local QA (grams shown to the customer)."""

    email: str = Field(min_length=3, max_length=320)
    balance_rice_g: int | None = Field(
        default=None,
        description="Bowl rice in grams; negative becomes 0g + arrears.",
    )
    arrears_rice_g: int | None = Field(
        default=None,
        description="Owed rice in grams; omit or null to leave unchanged.",
    )
    disable_bot_if_empty: bool = True
    enable_bot_if_active: bool = True

    @field_validator("balance_rice_g", "arrears_rice_g", mode="before")
    @classmethod
    def _optional_grams(cls, value: object) -> object:
        """Swagger UI may send empty strings for optional numbers."""
        if value == "" or value is None:
            return None
        return value


class AdminWalletPublic(BaseModel):
    """Wallet snapshot for admin tools."""

    user_id: str
    email: str
    balance_yuan: Decimal
    balance_rice_g: int
    arrears_yuan: Decimal
    arrears_rice_g: int
    status: str
    adapter_id: str | None = None


class BindingManualRequest(BaseModel):
    """Customer-pasted QQ credentials (advanced path)."""

    qq_appid: str = Field(min_length=4, max_length=64)
    app_secret: str = Field(min_length=4, max_length=256)


class BindingPublic(BaseModel):
    id: str
    channel: str = "qq"
    qq_appid: str | None
    adapter_id: str
    umo_prefix: str
    bind_status: str

    model_config = {"from_attributes": True}


class BindMetaPublic(BaseModel):
    """Hints shown on the bind wizard (no secrets)."""

    qq_egress_ip: str = ""
    astrbot_ready: bool = False
    channels: list[str] = Field(default_factory=lambda: ["qq", "weixin"])


class QrStartRequest(BaseModel):
    channel: str = Field(default="qq", max_length=16)


class QrStartPublic(BaseModel):
    session_id: str
    channel: str
    qrcode: str
    interval: int
    expires_in: int


class QrPollRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)


class QrPollPublic(BaseModel):
    status: str
    message: str | None = None
    binding: BindingPublic | None = None


class UsageRow(BaseModel):
    date: str
    model: str
    rice_g: int
    calls: int


class UsageSummary(BaseModel):
    days: int
    rows: list[UsageRow]
    total_rice_g: int
    bound: bool


class TicketCreateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)


class TicketPublic(BaseModel):
    id: str
    subject: str
    body: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfilePublic(BaseModel):
    email: str
    paid: bool
    wallet: WalletPublic
    binding: BindingPublic | None
