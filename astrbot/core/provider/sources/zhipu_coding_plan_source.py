from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial

ZHIPU_CODING_PLAN_API_BASE = "https://open.bigmodel.cn/api/coding/paas/v4"
ZHIPU_CODING_PLAN_GLOBAL_API_BASE = "https://api.z.ai/api/coding/paas/v4"
ZHIPU_CODING_PLAN_DEFAULT_MODEL = "glm-5.3"
ZHIPU_CODING_PLAN_MODELS = [
    "glm-5.3",
    "glm-5.3-flash",
    "glm-5.2",
    "glm-5-turbo",
    "glm-5v-turbo",
    "glm-5.1",
    "glm-4.7",
]


def _apply_reasoning_policy(model: str, extra_body: dict) -> None:
    requested = str(extra_body.get("reasoning_effort", "")).strip().lower()
    normalized_model = model.strip().lower()

    if normalized_model.startswith("glm-5.3"):
        requested = requested or "max"
        effort_map = {
            "off": "low",
            "none": "low",
            "minimal": "low",
            "low": "low",
            "medium": "high",
            "high": "high",
            "xhigh": "max",
            "adaptive": "max",
            "max": "max",
            "ultra": "max",
        }
        extra_body["reasoning_effort"] = effort_map.get(requested, requested)
        thinking = extra_body.get("thinking")
        if isinstance(thinking, dict) and thinking.get("type") == "disabled":
            extra_body.pop("thinking", None)
        return

    if normalized_model.startswith("glm-5.2"):
        thinking = extra_body.get("thinking")
        if not requested and isinstance(thinking, dict):
            if thinking.get("type") == "enabled":
                return
        requested = requested or "off"
        if requested in {"off", "none"}:
            extra_body.pop("reasoning_effort", None)
            extra_body["thinking"] = {"type": "disabled"}
            return
        effort_map = {
            "low": "high",
            "medium": "high",
            "high": "high",
            "adaptive": "high",
            "xhigh": "max",
            "max": "max",
            "ultra": "max",
        }
        extra_body["reasoning_effort"] = effort_map.get(requested, requested)
        thinking = extra_body.get("thinking")
        if isinstance(thinking, dict) and thinking.get("type") == "disabled":
            extra_body.pop("thinking", None)
        return

    extra_body.pop("reasoning_effort", None)


@register_provider_adapter(
    "zhipu_coding_plan_chat_completion",
    "Zhipu Coding Plan Provider Adapter",
)
class ProviderZhipuCodingPlan(ProviderOpenAIOfficial):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        merged_provider_config = dict(provider_config)
        if not str(merged_provider_config.get("api_base") or "").strip():
            merged_provider_config["api_base"] = ZHIPU_CODING_PLAN_API_BASE
        if not str(merged_provider_config.get("model") or "").strip():
            merged_provider_config["model"] = ZHIPU_CODING_PLAN_DEFAULT_MODEL

        configured_extra_body = merged_provider_config.get("custom_extra_body")
        merged_provider_config["custom_extra_body"] = (
            dict(configured_extra_body)
            if isinstance(configured_extra_body, dict)
            else {}
        )

        super().__init__(merged_provider_config, provider_settings)

    def _apply_provider_specific_request_overrides(
        self,
        payloads: dict,
        extra_body: dict,
    ) -> None:
        super()._apply_provider_specific_request_overrides(payloads, extra_body)
        request_reasoning_effort = payloads.pop("reasoning_effort", None)
        if request_reasoning_effort is not None:
            extra_body["reasoning_effort"] = request_reasoning_effort
        _apply_reasoning_policy(str(payloads.get("model", "")), extra_body)

    async def _query_stream(
        self,
        payloads: dict,
        tools,
        *,
        request_max_retries: int | None = None,
    ):
        stream_payloads = dict(payloads)
        custom_extra_body = self.provider_config.get("custom_extra_body", {})
        tool_stream_disabled = (
            isinstance(custom_extra_body, dict)
            and custom_extra_body.get("tool_stream") is False
        )
        if tools and not tool_stream_disabled:
            stream_payloads.setdefault("tool_stream", True)

        async for response in super()._query_stream(
            stream_payloads,
            tools,
            request_max_retries=request_max_retries,
        ):
            yield response

    async def get_models(self) -> list[str]:
        return ZHIPU_CODING_PLAN_MODELS.copy()
