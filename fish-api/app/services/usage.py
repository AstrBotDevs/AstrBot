from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.wallet import BotBinding
from app.providers.model_cost import usd_cost_from_tokens
from app.services.rice import display_rice_grams_from_usd

SERVICE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SERVICE_ROOT.parent


def resolve_astrbot_db_url() -> str | None:
    """Resolve AstrBot SQLite URL for read-only usage queries."""
    raw = (settings.astrbot_database_url or "").strip()
    if raw:
        return raw
    default_path = (REPO_ROOT / "data" / "data_v4.db").resolve()
    if default_path.is_file():
        return f"sqlite:///{default_path}"
    return None


def query_usage_rows(
    umo_prefix: str,
    days: int = 7,
) -> list[dict[str, object]]:
    """Aggregate provider_stats by day and model for a umo prefix.

    Rice grams are derived from real USD model cost × display multiplier,
    not from a flat tokens→yuan placeholder.
    """
    db_url = resolve_astrbot_db_url()
    if not db_url:
        return []
    since = datetime.now(UTC) - timedelta(days=max(1, min(days, 30)))
    since_iso = since.strftime("%Y-%m-%d %H:%M:%S")
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False}
        if db_url.startswith("sqlite")
        else {},
    )
    sql = text(
        """
        SELECT
            date(created_at) AS day,
            COALESCE(provider_model, 'unknown') AS model,
            COALESCE(provider_id, '') AS provider_id,
            SUM(token_input_other) AS token_input_other,
            SUM(token_input_cached) AS token_input_cached,
            SUM(token_output) AS token_output,
            COUNT(*) AS calls
        FROM provider_stats
        WHERE agent_type = 'internal'
          AND umo LIKE :umo_prefix
          AND created_at >= :since_iso
        GROUP BY day, model, provider_id
        ORDER BY day DESC, model
        """
    )
    rows: list[dict[str, object]] = []
    with engine.connect() as conn:
        result = conn.execute(
            sql,
            {"umo_prefix": f"{umo_prefix}%", "since_iso": since_iso},
        )
        for row in result.mappings():
            usd = usd_cost_from_tokens(
                model=str(row["model"]),
                provider_id=str(row["provider_id"] or "") or None,
                token_input_other=int(row["token_input_other"] or 0),
                token_input_cached=int(row["token_input_cached"] or 0),
                token_output=int(row["token_output"] or 0),
            )
            rows.append(
                {
                    "date": str(row["day"]),
                    "model": str(row["model"]),
                    "rice_g": display_rice_grams_from_usd(usd),
                    "calls": int(row["calls"] or 0),
                }
            )
    return rows


def get_binding_or_none(db: Session, user_id: str) -> BotBinding | None:
    """Return the user's bot binding if present."""
    from sqlalchemy import select

    return db.scalar(select(BotBinding).where(BotBinding.user_id == user_id))
