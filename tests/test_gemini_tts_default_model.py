from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.core.provider.sources.gemini_tts_source import ProviderGeminiTTSAPI

RETIRING_MODEL = "gemini-2.5-flash-preview-tts"


def _template_model() -> str:
    templates = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]
    return templates["Gemini TTS"]["gemini_tts_model"]


def test_gemini_tts_template_default_is_not_the_retiring_preview():
    assert _template_model() != RETIRING_MODEL


def test_gemini_tts_provider_default_matches_the_template():
    provider = ProviderGeminiTTSAPI({"id": "gemini_tts", "gemini_tts_api_key": "k"}, {})
    assert provider.model == _template_model() == "gemini-3.8-flash-tts"
