import pytest

import astrbot.api  # noqa: F401  # Initialize API before provider adapters.
from astrbot.core.provider.sources.gsv_selfhosted_source import ProviderGSVTTS


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("ref_audio_path", "/Voices/Alice.WAV", "/Voices/Alice.WAV"),
        ("prompt_text", "Hello NASA", "Hello NASA"),
        ("streaming_mode", True, "true"),
        ("parallel_infer", False, "false"),
        ("top_k", 5, "5"),
        ("speed_factor", 1.25, "1.25"),
    ],
)
def test_synthesis_params_preserve_case_and_serialize_scalars(key, value, expected):
    provider = ProviderGSVTTS({"gsv_default_parms": {f"gsv_{key}": value}}, {})

    params = provider.build_synthesis_params("Read NASA aloud")

    assert params[key] == expected
    assert params["text"] == "Read NASA aloud"
