from astrbot.core.provider.fallbacks import prune_fallback_chat_models


def test_prune_fallback_chat_models_removes_disabled_missing_and_duplicate_ids():
    config = {
        "provider": [
            {
                "id": "enabled-chat",
                "provider_type": "chat_completion",
                "enable": True,
            },
            {
                "id": "disabled-chat",
                "provider_type": "chat_completion",
                "enable": False,
            },
            {
                "id": "tts-provider",
                "provider_type": "text_to_speech",
                "enable": True,
            },
        ],
        "provider_settings": {
            "fallback_chat_models": [
                "enabled-chat",
                "disabled-chat",
                "missing-chat",
                "tts-provider",
                "enabled-chat",
                "",
            ],
        },
    }

    removed_ids = prune_fallback_chat_models(config)

    assert config["provider_settings"]["fallback_chat_models"] == ["enabled-chat"]
    assert removed_ids == [
        "disabled-chat",
        "missing-chat",
        "tts-provider",
        "enabled-chat",
        "",
    ]


def test_prune_fallback_chat_models_ignores_non_list_setting():
    config = {
        "provider": [{"id": "enabled-chat", "enable": True}],
        "provider_settings": {"fallback_chat_models": "enabled-chat"},
    }

    removed_ids = prune_fallback_chat_models(config)

    assert config["provider_settings"]["fallback_chat_models"] == "enabled-chat"
    assert removed_ids == []


def test_prune_fallback_chat_models_uses_provider_source_type():
    config = {
        "provider_sources": [
            {"id": "chat-source", "provider_type": "chat_completion"},
            {"id": "legacy-chat-source"},
            {"id": "empty-chat-source", "provider_type": ""},
            {"id": "embedding-source", "provider_type": "embedding"},
        ],
        "provider": [
            {
                "id": "chat-model",
                "provider_source_id": "chat-source",
                "enable": True,
            },
            {
                "id": "legacy-chat-model",
                "provider_source_id": "legacy-chat-source",
                "enable": True,
            },
            {
                "id": "empty-chat-model",
                "provider_source_id": "empty-chat-source",
                "enable": True,
            },
            {
                "id": "inline-legacy-chat",
                "enable": True,
            },
            {
                "id": "embedding-model",
                "provider_source_id": "embedding-source",
                "enable": True,
            },
            {
                "id": "missing-source-model",
                "provider_source_id": "missing-source",
                "enable": True,
            },
        ],
        "provider_settings": {
            "fallback_chat_models": [
                "chat-model",
                "legacy-chat-model",
                "empty-chat-model",
                "inline-legacy-chat",
                "embedding-model",
                "missing-source-model",
            ],
        },
    }

    removed_ids = prune_fallback_chat_models(config)

    assert config["provider_settings"]["fallback_chat_models"] == [
        "chat-model",
        "legacy-chat-model",
        "empty-chat-model",
        "inline-legacy-chat",
    ]
    assert removed_ids == ["embedding-model", "missing-source-model"]
