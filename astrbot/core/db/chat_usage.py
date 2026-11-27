"""Read historical turn totals alongside the request-level chat ledger."""

from sqlalchemy import literal, union_all
from sqlmodel import func, select

from .po import ChatRequestStat, ProviderStat

# Native turns stopped writing ProviderStat when the request ledger was added.
# Historical rows retain their original per-turn measurements.
chat_usage = union_all(
    select(
        ChatRequestStat.created_at,
        ChatRequestStat.umo,
        ChatRequestStat.conversation_id,
        ChatRequestStat.plugin_id,
        ChatRequestStat.provider_id,
        ChatRequestStat.provider_model,
        ChatRequestStat.token_input_other,
        ChatRequestStat.token_input_cached,
        ChatRequestStat.token_output,
        ChatRequestStat.status,
        ChatRequestStat.duration,
        ChatRequestStat.time_to_first_token,
        literal(True).label("is_request"),
    ),
    select(
        ProviderStat.created_at,
        ProviderStat.umo,
        ProviderStat.conversation_id,
        literal(None).label("plugin_id"),
        ProviderStat.provider_id,
        ProviderStat.provider_model,
        ProviderStat.token_input_other,
        ProviderStat.token_input_cached,
        ProviderStat.token_output,
        ProviderStat.status,
        (ProviderStat.end_time - ProviderStat.start_time).label("duration"),
        func.nullif(ProviderStat.time_to_first_token, 0).label("time_to_first_token"),
        literal(False).label("is_request"),
    ).where(ProviderStat.agent_type == "internal"),
).subquery("chat_usage")
