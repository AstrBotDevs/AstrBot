"""Environment whitelist for plugin Runner subprocesses.

Runners must not inherit the host environment: it carries LLM API keys,
database credentials, and dashboard secrets. The whitelist passes only
what a Python process and plugin-spawned subprocesses need to function
(locale, temp dirs, PATH, proxies, CA overrides); plugin-specific
configuration travels through the plugin config channel instead.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

# Keys inherited from the host environment when present. PYTHONPATH and
# other PYTHON* variables are deliberately excluded: they would pollute the
# plugin venv's import resolution.
RUNNER_ENV_KEYS = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TMPDIR",
    "TEMP",
    "TMP",
    "SYSTEMROOT",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
)


def runner_env(
    extra: Mapping[str, str] | None = None,
    *,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the whitelisted environment for one Runner subprocess.

    Args:
        extra: Explicit additions and overrides applied last (e.g.
            ASTRBOT_DATA_PATH). May intentionally add anything; only the
            inherited part is restricted.
        base: Environment to filter; defaults to os.environ (injectable
            for tests).

    Returns:
        The environment for the Runner process.
    """
    source = os.environ if base is None else base
    env = {key: source[key] for key in RUNNER_ENV_KEYS if key in source}
    # Keep the user site directory out of plugin venvs.
    env["PYTHONNOUSERSITE"] = "1"
    env.update(extra or {})
    return env
