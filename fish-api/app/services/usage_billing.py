"""Sync AstrBot provider_stats into fish wallet (deduct rice / suspend)."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.wallet import WalletAccount
from app.providers.astrbot import AstrBotClient, AstrBotClientError
from app.providers.model_cost import usd_cost_from_tokens
from app.services.rice import internal_yuan_from_usd_charge
from app.services.usage import get_binding_or_none, resolve_astrbot_db_url
from app.services.wallet import get_or_create_wallet, settle_arrears_from_balance

logger = logging.getLogger(__name__)


def _fetch_unsynced_stats(
    umo_prefix: str,
    after_id: int,
) -> list[dict[str, object]]:
    """Load provider_stats rows newer than the billing cursor."""
    db_url = resolve_astrbot_db_url()
    if not db_url:
        return []
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False}
        if db_url.startswith("sqlite")
        else {},
    )
    sql = text(
        """
        SELECT
            id,
            COALESCE(provider_model, 'unknown') AS model,
            COALESCE(provider_id, '') AS provider_id,
            token_input_other,
            token_input_cached,
            token_output
        FROM provider_stats
        WHERE agent_type = 'internal'
          AND umo LIKE :umo_prefix
          AND id > :after_id
        ORDER BY id ASC
        """
    )
    with engine.connect() as conn:
        result = conn.execute(
            sql,
            {"umo_prefix": f"{umo_prefix}%", "after_id": int(after_id or 0)},
        )
        return [dict(row) for row in result.mappings()]


def apply_usage_debit(wallet: WalletAccount, debit: Decimal) -> bool:
    """Subtract internal yuan; return True when bowl becomes empty / suspended.

    Args:
        wallet: Wallet row to mutate.
        debit: Internal-yuan amount matching display rice charge.

    Returns:
        True if status should trigger disabling the AstrBot bot now.
    """
    if debit <= 0:
        return False
    debit = debit.quantize(Decimal("0.0001"))
    was_serving = wallet.status == "active" and wallet.balance_yuan > 0
    if wallet.balance_yuan >= debit:
        wallet.balance_yuan = (wallet.balance_yuan - debit).quantize(Decimal("0.0001"))
    else:
        short = (debit - wallet.balance_yuan).quantize(Decimal("0.0001"))
        wallet.arrears_yuan = (wallet.arrears_yuan + short).quantize(Decimal("0.0001"))
        wallet.balance_yuan = Decimal("0.0000")

    if wallet.balance_yuan <= 0:
        wallet.balance_yuan = Decimal("0.0000")
        wallet.status = "suspended_arrears"
        return was_serving
    return False


def _disable_bot_best_effort(adapter_id: str) -> None:
    """Turn off AstrBot platform instance when rice runs out."""
    client = AstrBotClient()
    if not client.configured() or not adapter_id:
        return

    async def _run() -> None:
        await client.set_bot_enabled(adapter_id, False)

    try:
        asyncio.run(_run())
        logger.info("Disabled AstrBot bot %s (out of rice)", adapter_id)
    except AstrBotClientError as exc:
        logger.warning("Failed to disable bot %s after out-of-rice: %s", adapter_id, exc)
    except Exception as exc:  # noqa: BLE001 — never fail wallet sync on disable
        logger.warning("Failed to disable bot %s after out-of-rice: %s", adapter_id, exc)


def sync_usage_charges(db: Session, user: User) -> WalletAccount:
    """Bill unsynced provider_stats into the user's wallet.

    Called on wallet/profile reads so the饭碗 shows remaining rice without a
    separate cron. Safe to call repeatedly; cursor advances only after debit.
    When rice is gone, disable the bound AstrBot bot on 6185.
    """
    wallet = get_or_create_wallet(db, user.id)
    binding = get_binding_or_none(db, user.id)
    if binding is None or binding.bind_status != "active":
        return wallet

    was_serving = wallet.status == "active" and wallet.balance_yuan > 0
    rows = _fetch_unsynced_stats(binding.umo_prefix, binding.usage_synced_stat_id)
    should_disable = False
    if rows:
        total_usd = 0.0
        max_id = int(binding.usage_synced_stat_id or 0)
        for row in rows:
            total_usd += usd_cost_from_tokens(
                model=str(row.get("model") or "unknown"),
                provider_id=str(row.get("provider_id") or "") or None,
                token_input_other=int(row.get("token_input_other") or 0),
                token_input_cached=int(row.get("token_input_cached") or 0),
                token_output=int(row.get("token_output") or 0),
            )
            max_id = max(max_id, int(row["id"]))

        debit = internal_yuan_from_usd_charge(total_usd)
        should_disable = apply_usage_debit(wallet, debit)
        binding.usage_synced_stat_id = max_id
        db.add(wallet)
        db.add(binding)
        db.flush()

    # Bowl already empty but still marked active (e.g. legacy row): suspend once.
    if wallet.balance_yuan <= 0 and wallet.status == "active":
        wallet.status = "suspended_arrears"
        db.add(wallet)
        db.flush()
        should_disable = was_serving or should_disable

    if should_disable:
        _disable_bot_best_effort(binding.adapter_id)

    return wallet


def enforce_bot_for_wallet(db: Session, user: User, *, enable_if_active: bool = True) -> None:
    """After manual wallet edits: suspend + disable bot, or resume + enable."""
    wallet = get_or_create_wallet(db, user.id)
    binding = get_binding_or_none(db, user.id)
    if binding is None or binding.bind_status != "active":
        return

    settle_arrears_from_balance(wallet)
    db.add(wallet)
    db.flush()

    if wallet.balance_yuan <= 0:
        wallet.status = "suspended_arrears"
        db.add(wallet)
        db.flush()
        _disable_bot_best_effort(binding.adapter_id)
        return

    if wallet.arrears_yuan > 0:
        wallet.status = "suspended_arrears"
        db.add(wallet)
        db.flush()
        _disable_bot_best_effort(binding.adapter_id)
        return

    wallet.status = "active"
    db.add(wallet)
    db.flush()
    if enable_if_active:
        client = AstrBotClient()
        if client.configured():
            try:
                asyncio.run(client.set_bot_enabled(binding.adapter_id, True))
                logger.info("Enabled AstrBot bot %s after wallet resume", binding.adapter_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to enable bot %s after wallet restore: %s",
                    binding.adapter_id,
                    exc,
                )
