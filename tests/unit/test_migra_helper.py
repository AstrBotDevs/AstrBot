import json

from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.utils.migra_helper import _prune_invalid_provider_source_models


def test_prune_invalid_provider_source_models_removes_unresolvable_entries(tmp_path):
    config_path = tmp_path / "cmd_config.json"
    config_path.write_text(
        json.dumps(
            {
                "provider_sources": [
                    {
                        "id": "valid_source",
                        "type": "openai_chat_completion",
                        "provider_type": "chat_completion",
                    },
                    {"id": "broken_source"},
                ],
                "provider": [
                    {
                        "id": "valid-model",
                        "provider_source_id": "valid_source",
                        "model": "gpt-test",
                        "enable": True,
                    },
                    {
                        "id": "missing-source-model",
                        "provider_source_id": "missing_source",
                        "model": "stale",
                        "enable": True,
                    },
                    {
                        "id": "broken-source-model",
                        "provider_source_id": "broken_source",
                        "model": "stale",
                        "enable": True,
                    },
                    {
                        "id": "legacy-direct-provider",
                        "type": "openai_chat_completion",
                        "model": "gpt-test",
                        "enable": True,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )

    conf = AstrBotConfig(
        config_path=str(config_path),
        default_config={"provider_sources": [], "provider": []},
    )

    _prune_invalid_provider_source_models(conf)

    provider_ids = [provider["id"] for provider in conf["provider"]]
    assert provider_ids == ["valid-model", "legacy-direct-provider"]

    saved = json.loads(config_path.read_text(encoding="utf-8-sig"))
    saved_ids = [provider["id"] for provider in saved["provider"]]
    assert saved_ids == provider_ids
