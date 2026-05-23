import pytest

from astrbot.core.provider.sources.openai_oauth_source import ProviderOpenAIOAuth


def _make_provider(overrides: dict | None = None) -> ProviderOpenAIOAuth:
    provider_config = {
        "id": "test-openai-oauth",
        "type": "openai_oauth_chat_completion",
        "model": "gpt-5.4",
        "oauth_access_token": "test-token",
        "oauth_account_id": "test-account",
    }
    if overrides:
        provider_config.update(overrides)
    return ProviderOpenAIOAuth(
        provider_config=provider_config,
        provider_settings={},
    )


@pytest.mark.asyncio
async def test_parse_backend_response_rehydrates_sse_output_items():
    provider = _make_provider()
    try:
        text = """
event: response.output_text.done
data: {"type":"response.output_text.done","content_index":0,"item_id":"msg_test","output_index":0,"sequence_number":6,"text":"PONG"}

event: response.output_item.done
data: {"type":"response.output_item.done","item":{"id":"msg_test","type":"message","status":"completed","content":[{"type":"output_text","annotations":[],"logprobs":[],"text":"PONG"}],"phase":"final_answer","role":"assistant"},"output_index":0,"sequence_number":8}

event: response.completed
data: {"type":"response.completed","response":{"id":"resp_test","object":"response","created_at":1775575895,"status":"completed","background":false,"completed_at":1775575901,"error":null,"model":"gpt-5.4","output":[],"parallel_tool_calls":true,"reasoning":{"effort":"none","summary":null},"service_tier":"default","store":false,"temperature":1.0,"text":{"format":{"type":"text"},"verbosity":"medium"},"tool_choice":"auto","tool_usage":{"image_gen":{"input_tokens":0,"input_tokens_details":{"image_tokens":0,"text_tokens":0},"output_tokens":0,"output_tokens_details":{"image_tokens":0,"text_tokens":0},"total_tokens":0},"web_search":{"num_requests":0}},"tools":[],"top_logprobs":0,"top_p":0.98,"truncation":"disabled","usage":{"input_tokens":12,"input_tokens_details":{"cached_tokens":0},"output_tokens":6,"output_tokens_details":{"reasoning_tokens":0},"total_tokens":18},"user":null,"metadata":{}},"sequence_number":9}
""".strip()

        response = provider._parse_backend_response(text)
        llm_response = await provider._parse_responses_completion(response, None)

        assert llm_response.completion_text == "PONG"
        assert response["output_text"] == "PONG"
        assert response["output"][0]["content"][0]["text"] == "PONG"
        assert llm_response.usage is not None
        assert llm_response.usage.output == 6
    finally:
        await provider.terminate()
