"""A cleared FishAudio ``timeout`` must not break every TTS request.

``timeout`` is a dashboard numeric field (``astrbot/core/config/default.py``
declares it with ``"type": "int"``), and the dashboard writes ``0`` when such a
field is cleared, while an empty ``timeout:`` in a hand-edited provider config
loads as ``None``.  httpx reads a non-positive timeout as "expire immediately" -
measured with a local server that answers after 0.4s: ``AsyncClient(timeout=0)``
raises ``ConnectTimeout`` whose ``str()`` is empty, while ``timeout=20`` returns
200 - so ``get_audio`` failed on every synthesis with a blank error message, and
``None`` escaped the original ``except ValueError`` and aborted provider
construction with a bare ``TypeError``.
"""

import pytest

from astrbot.core.provider.sources.fishaudio_tts_api_source import (
    ProviderFishAudioTTSAPI,
)

# The default documented in astrbot/core/config/default.py.
EXPECTED_DEFAULT = 20

BASE_CONFIG = {"api_key": "test-key", "model": "s2-pro"}


def _provider(**overrides) -> ProviderFishAudioTTSAPI:
    return ProviderFishAudioTTSAPI({**BASE_CONFIG, **overrides}, {})


@pytest.mark.parametrize(
    "timeout",
    [0, -5, 0.4, None, "", "abc", float("inf")],
)
def test_unusable_timeout_falls_back_to_default(timeout):
    assert _provider(timeout=timeout).timeout == EXPECTED_DEFAULT


@pytest.mark.parametrize("timeout", [45, "45", 45.9])
def test_positive_timeout_is_kept(timeout):
    assert _provider(timeout=timeout).timeout == 45


def test_missing_timeout_uses_default():
    assert _provider().timeout == EXPECTED_DEFAULT
