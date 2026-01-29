"""供应商/Provider 相关的默认配置"""

# 供应商默认配置
PROVIDERS_DEFAULT_CONFIG = {
    "provider_sources": [],  # provider sources
    "provider": [],  # models from provider_sources
    "provider_settings": {
        "enable": True,
        "default_provider_id": "",
        "default_image_caption_provider_id": "",
        "image_caption_prompt": "Please describe the image using Chinese.",
        "provider_pool": ["*"],  # "*" 表示使用所有可用的提供者
        "wake_prefix": "",
        "web_search": False,
        "websearch_provider": "default",
        "websearch_tavily_key": [],
        "websearch_baidu_app_builder_key": "",
        "web_search_link": False,
        "display_reasoning_text": False,
        "identifier": False,
        "group_name_display": False,
        "datetime_system_prompt": True,
        "default_personality": "default",
        "persona_pool": ["*"],
        "prompt_prefix": "{{prompt}}",
        "context_limit_reached_strategy": "truncate_by_turns",  # or llm_compress
        "llm_compress_instruction": (
            "Based on our full conversation history, produce a concise summary of key takeaways and/or project progress.\n"
            "1. Systematically cover all core topics discussed and the final conclusion/outcome for each; clearly highlight the latest primary focus.\n"
            "2. If any tools were used, summarize tool usage (total call count) and extract the most valuable insights from tool outputs.\n"
            "3. If there was an initial user goal, state it first and describe the current progress/status.\n"
            "4. Write the summary in the user's language.\n"
        ),
        "llm_compress_keep_recent": 4,
        "llm_compress_provider_id": "",
        "max_context_length": -1,
        "dequeue_context_length": 1,
        "streaming_response": False,
        "show_tool_use_status": False,
        "sanitize_context_by_modalities": False,
        "agent_runner_type": "local",
        "dify_agent_runner_provider_id": "",
        "coze_agent_runner_provider_id": "",
        "dashscope_agent_runner_provider_id": "",
        "unsupported_streaming_strategy": "realtime_segmenting",
        "reachability_check": False,
        "max_agent_step": 30,
        "tool_call_timeout": 60,
        "tool_schema_mode": "full",
        "llm_safety_mode": True,
        "safety_mode_strategy": "system_prompt",  # TODO: llm judge
        "file_extract": {
            "enable": False,
            "provider": "moonshotai",
            "moonshotai_api_key": "",
        },
        "sandbox": {
            "enable": False,
            "booter": "shipyard",
            "shipyard_endpoint": "",
            "shipyard_access_token": "",
            "shipyard_ttl": 3600,
            "shipyard_max_sessions": 10,
        },
        "skills": {"runtime": "sandbox"},
    },
    "provider_stt_settings": {
        "enable": False,
        "provider_id": "",
    },
    "provider_tts_settings": {
        "enable": False,
        "provider_id": "",
        "dual_output": False,
        "use_file_service": False,
        "trigger_probability": 1.0,
    },
    "provider_ltm_settings": {
        "group_icl_enable": False,
        "group_message_max_cnt": 300,
        "image_caption": False,
        "image_caption_provider_id": "",
        "active_reply": {
            "enable": False,
            "method": "possibility_reply",
            "possibility_reply": 0.1,
            "whitelist": [],
        },
    },
}

# 供应商配置的键列表（用于迁移检测）
PROVIDERS_CONFIG_KEYS = [
    "provider_sources",
    "provider",
    "provider_settings",
    "provider_stt_settings",
    "provider_tts_settings",
    "provider_ltm_settings",
]
