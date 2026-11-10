from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FISH_",
        extra="ignore",
    )

    env: str = "development"
    database_url: str = "sqlite:///./data/fish.db"
    jwt_secret: str = "dev-only-change-in-production"
    jwt_expire_minutes: int = 60 * 24 * 7
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    topup_credit_ratio: float = 0.5
    min_topup_yuan: float = 1.0
    usage_display_multiplier: float = 2.0
    # User-facing: grams per 1 Alipay pay-yuan (not per internal APIKEY yuan).
    rice_grams_per_yuan: float = 500.0
    # Placeholder until provider_stats carries yuan; internal APIKEY cost estimate.
    internal_yuan_per_million_tokens: float = 1.0
    astrbot_database_url: str = ""
    alipay_qr_url: str = ""
    alipay_pay_hint: str = "转账金额须与本次添饭一致，备注请原样填写下方备注码。"
    admin_api_key: str = ""
    admin_emails: str = ""
    auto_confirm_orders: bool = False
    feed_plan_yuan_1: int = 2
    feed_plan_yuan_2: int = 5
    feed_plan_yuan_3: int = 20
    feed_plan_name_1: str = "唔饿啦"
    feed_plan_name_2: str = "贴贴罐"
    feed_plan_name_3: str = "饱饱桶"

    def feed_plans_public(self) -> list[dict[str, int | str]]:
        """Preset rice packs (yuan); env suffix _1/_2/_3 = tier, not amount."""
        blurbs = (
            "先垫一口，我醒醒神",
            "日常饭量，够吃好几天",
            "吃饱了才有力气干活（真的）",
        )
        tiers = (
            (1, self.feed_plan_yuan_1, self.feed_plan_name_1, blurbs[0]),
            (2, self.feed_plan_yuan_2, self.feed_plan_name_2, blurbs[1]),
            (3, self.feed_plan_yuan_3, self.feed_plan_name_3, blurbs[2]),
        )
        return [
            {
                "id": f"feed-{tier}-{yuan}",
                "yuan": yuan,
                "name": name,
                "blurb": blurb,
            }
            for tier, yuan, name, blurb in tiers
        ]

    @property
    def cors_origin_list(self) -> list[str]:
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]

    def resolve_sqlite_path(self, base_dir: Path) -> str:
        """Expand relative SQLite paths against the service root."""
        if not self.database_url.startswith("sqlite"):
            return self.database_url
        raw = self.database_url.removeprefix("sqlite:///")
        path = Path(raw)
        if not path.is_absolute():
            path = (base_dir / raw).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{path}"
        return self.database_url


settings = Settings()
