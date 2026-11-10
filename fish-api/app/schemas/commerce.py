from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


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


class BindingUpsertRequest(BaseModel):
    qq_appid: str = Field(min_length=4, max_length=64)
    adapter_id: str = Field(min_length=2, max_length=128)
    umo_prefix: str | None = Field(default=None, max_length=256)


class BindingPublic(BaseModel):
    id: str
    qq_appid: str | None
    adapter_id: str
    umo_prefix: str
    bind_status: str

    model_config = {"from_attributes": True}


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
