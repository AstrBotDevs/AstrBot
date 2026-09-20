import json
import re
from collections.abc import AsyncGenerator
from uuid import uuid4

import httpx
import jsonschema
from openai.types.chat.chat_completion import ChatCompletion

from astrbot.core.agent.tool import ToolSet
from astrbot.core.provider.entities import LLMResponse

from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "dots_chat_completion", "Dots Chat Completion Provider Adapter"
)
class ProviderDots(ProviderOpenAIOfficial):
    """Use the Dots OpenAI-compatible API."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """Initialize the provider with Dots defaults.

        Args:
            provider_config: Provider source and model configuration.
            provider_settings: Global provider settings.
        """
        provider_config = provider_config.copy()
        if not provider_config.get("api_base"):
            provider_config["api_base"] = "https://note3-prev-api.askdiandian.com/v1"
        provider_config.setdefault("model", "dots3-note-prev")
        super().__init__(provider_config, provider_settings)

    def _create_http_client(self, provider_config: dict) -> httpx.AsyncClient:
        """Add Dots authentication alongside the SDK's per-request bearer key.

        Args:
            provider_config: Provider configuration, including proxy settings.

        Returns:
            HTTP client with a request hook that follows SDK key rotation.
        """
        client = super()._create_http_client(provider_config)

        async def add_api_key(request: httpx.Request) -> None:
            """Set the API key from the already-built request.

            Args:
                request: Outgoing SDK request with its selected bearer key.
            """
            # Read the request rather than mutable client state during concurrent calls.
            authorization = request.headers.get("Authorization", "")
            if authorization.startswith("Bearer "):
                request.headers["api-key"] = authorization.removeprefix("Bearer ")

        client.event_hooks["request"].append(add_api_key)
        return client

    def _parse_dots_block(self, body: str, tools: ToolSet) -> list[dict]:
        """Decode a Dots call block and validate its declared tool arguments.

        Args:
            body: XML invoke elements or a JSON call object inside the wrapper.
            tools: Tools available for this request.

        Returns:
            Standard OpenAI function call dictionaries.

        Raises:
            ValueError: The block, tool name, or arguments are invalid.
        """
        calls = []
        if body.lstrip().startswith("{"):
            try:
                call = json.loads(body)
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid Dots JSON tool call") from exc
            calls.append(
                (call.get("name"), call.get("arguments", call.get("parameters", {})))
            )
        else:
            invoke_pattern = re.compile(
                r"<invoke\s+name\s*=\s*(['\"])(.*?)\1\s*>(.*?)</invoke>",
                re.DOTALL,
            )
            parameter_pattern = re.compile(
                r"<parameter\s+name\s*=\s*(['\"])(.*?)\1\s*>(.*?)</parameter>",
                re.DOTALL,
            )
            if invoke_pattern.sub("", body).strip():
                raise ValueError("Invalid Dots XML tool call")
            for invocation in invoke_pattern.finditer(body):
                name, parameters = invocation.group(2, 3)
                tool = tools.get_tool(name)
                if tool is None or not tool.active:
                    raise ValueError("Dots requested an unavailable tool")
                if parameter_pattern.sub("", parameters).strip():
                    raise ValueError("Invalid Dots tool parameters")
                validator = jsonschema.validators.validator_for(tool.parameters)(
                    tool.parameters
                )
                args = {}
                for parameter in parameter_pattern.finditer(parameters):
                    param_name, value = parameter.group(2, 3)
                    if param_name in args:
                        raise ValueError("Duplicate Dots tool parameter")
                    schema = tool.parameters.get("properties", {}).get(param_name, {})
                    field_validator = validator.evolve(schema=schema)
                    value = value.strip()
                    if value == "null" and field_validator.is_valid(None):
                        args[param_name] = None
                    elif field_validator.is_valid(value):
                        args[param_name] = value
                    else:
                        try:
                            args[param_name] = json.loads(value)
                        except json.JSONDecodeError as exc:
                            raise ValueError(
                                "Invalid Dots tool parameter value"
                            ) from exc
                calls.append((name, args))

        if not calls:
            raise ValueError("Empty Dots tool call block")
        result = []
        for name, args in calls:
            tool = tools.get_tool(name) if isinstance(name, str) else None
            if tool is None or not tool.active:
                raise ValueError("Dots requested an unavailable tool")
            if not isinstance(args, dict):
                raise ValueError("Dots tool arguments must be an object")
            try:
                jsonschema.validate(args, tool.parameters)
                arguments = json.dumps(args, ensure_ascii=False, allow_nan=False)
            except (jsonschema.ValidationError, ValueError) as exc:
                raise ValueError(
                    "Dots tool arguments do not match the tool schema"
                ) from exc
            result.append(
                {
                    "id": f"call_{uuid4().hex}",
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            )
        return result

    async def _parse_openai_completion(
        self, completion: ChatCompletion, tools: ToolSet | None
    ) -> LLMResponse:
        """Normalize native calls when Dots explicitly requests tool execution.

        Args:
            completion: Complete API response, including assembled stream responses.
            tools: Tools available for this request.

        Returns:
            Parsed response with native call blocks removed from assistant text.

        Raises:
            ValueError: A requested native call is incomplete or invalid.
        """
        if not completion.choices:
            return await super()._parse_openai_completion(completion, tools)
        choice = completion.choices[0]
        content = choice.message.content or ""
        if (
            tools is not None
            and not tools.empty()
            and choice.finish_reason == "length"
            and "<dots_function_call" in content
        ):
            raise ValueError("Dots tool call was truncated by the output token limit")
        # Do not execute XML examples in ordinary assistant answers.
        if choice.finish_reason != "tool_calls":
            return await super()._parse_openai_completion(completion, tools)
        if "<dots_function_call>" not in content:
            if not choice.message.tool_calls:
                raise ValueError("Dots requested tools without a usable tool call")
            return await super()._parse_openai_completion(completion, tools)
        if tools is None or tools.empty():
            raise ValueError("Dots requested tools when no tools were provided")

        pattern = re.compile(
            r"<dots_function_call>(.*?)</dots_function_call>", re.DOTALL
        )
        blocks = list(pattern.finditer(content))
        clean_content = pattern.sub("", content).strip()
        if (
            not blocks
            or "<dots_function_call" in clean_content
            or "</dots_function_call>" in clean_content
        ):
            raise ValueError("Incomplete Dots tool call block")
        normalized = completion.model_dump()
        message = normalized["choices"][0]["message"]
        if not message.get("tool_calls"):
            calls = []
            for block in blocks:
                calls.extend(self._parse_dots_block(block.group(1), tools))
            message["tool_calls"] = calls
        # Standard calls are authoritative if both representations are present.
        message["content"] = clean_content or None
        return await super()._parse_openai_completion(
            ChatCompletion.model_validate(normalized), tools
        )

    async def _query_stream(
        self,
        payloads: dict,
        tools: ToolSet | None,
        *,
        request_max_retries: int | None = None,
    ) -> AsyncGenerator[LLMResponse, None]:
        """Buffer tool-enabled turns until native call normalization is complete.

        Args:
            payloads: Chat Completions request parameters.
            tools: Tools available for this request.
            request_max_retries: Maximum transport request attempts.

        Yields:
            Clean text chunks followed by the complete response.

        Raises:
            ValueError: A buffered stream ends without a valid final response.
        """
        buffer_output = tools is not None and not tools.empty()
        received_final = False
        async for response in super()._query_stream(
            payloads, tools, request_max_retries=request_max_retries
        ):
            if not buffer_output:
                yield response
                continue
            if response.is_chunk:
                continue
            received_final = True
            if response.completion_text or response.reasoning_content:
                yield LLMResponse(
                    "assistant",
                    completion_text=response.completion_text,
                    reasoning_content=response.reasoning_content,
                    is_chunk=True,
                    id=response.id,
                )
            yield response
        if buffer_output and not received_final:
            raise ValueError("Dots stream ended without a valid final response")
