"""Collect diagnostic metadata and redact credentials before serialization."""

from __future__ import annotations

import copy
import ipaddress
import json
import platform
import re
import subprocess
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import quote, quote_plus

from astrbot import __version__
from astrbot.core.utils.astrbot_path import get_astrbot_path

REDACTED = "[REDACTED]"
_SECRET_KEY = re.compile(
    r"password|passwd|secret|token$|api[_-]?key|access[_-]?key|private[_-]?key|"
    r"authorization|cookie|credential|(?:client|app|signing|encrypt(?:ion)?)[_-]?key|"
    r"recovery[_-]?code|(?:^|\.)key$|^headers$|^env$",
    re.IGNORECASE,
)
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_AUTH = re.compile(r"\b(Bearer|Basic|ApiKey)\s+[^\s\"'<>]+", re.IGNORECASE)
_COOKIE = re.compile(r"(\b(?:set-cookie|cookie)\s*:\s*)[^\r\n]+", re.IGNORECASE)
_URL_AUTH = re.compile(r"(https?://)[^/\s@]+@", re.IGNORECASE)
_ASSIGNMENT = re.compile(
    r"((?:[\w.-]*(?:token|secret|password|passwd|api[_-]?key|access[_-]?key|"
    r"(?:client|app|signing|encrypt(?:ion)?)[_-]?key|recovery[_-]?code)"
    r"[\w.-]*|authorization|cookie|\bkey)[\"']?\s*[:=]\s*)"
    r"(\"[^\"]*\"|'[^']*'|[^\s&,;}]+)",
    re.IGNORECASE,
)
_TOKEN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [\w ]*PRIVATE KEY-----.*?(?:-----END [\w ]*PRIVATE KEY-----|\Z)",
    re.DOTALL,
)
_IP_LITERAL = re.compile(
    r"(?<![\w.])(?:"
    r"\[[0-9a-fA-F:.]{2,45}(?:%[\w.-]{1,64})?\]|"
    r"(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F:.]{0,45}(?:%[\w.-]{1,64})?|"
    r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}"
    r")(?!\w|\.\w)"
)
MAX_LOG_LINE_BYTES = 1024 * 1024


class DiagnosticRedactor:
    """Share credentials and public IP aliases across every file in an export."""

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.secrets: set[str] = set()
        self.public_ips: dict[str, str] = {}

    def collect(self, value: Any, sensitive: bool = False) -> None:
        """Collect configured credentials without exporting their values.

        Args:
            value: Configuration or structured trace data.
            sensitive: Whether an ancestor denotes credentials.
        """
        if not self.enabled:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                self.collect(item, sensitive or bool(_SECRET_KEY.search(str(key))))
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.collect(item, sensitive)
        elif sensitive and value and not isinstance(value, bool):
            text = str(value)
            self.secrets.update(
                (text, quote(text, safe=""), quote_plus(text), json.dumps(text)[1:-1])
            )

    def redact(self, value: Any, sensitive: bool = False) -> Any:
        """Return a sanitized copy while retaining containers and boolean flags.

        Args:
            value: JSON-compatible diagnostic content.
            sensitive: Whether an ancestor denotes credentials.

        Returns:
            Data with credentials replaced and diagnostic values preserved.
        """
        if not self.enabled:
            return value
        if isinstance(value, dict):
            return {
                self.text(str(key)): self.redact(
                    item, sensitive or bool(_SECRET_KEY.search(str(key)))
                )
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self.redact(item, sensitive) for item in value]
        if isinstance(value, bool) or value is None:
            return value
        if sensitive:
            return REDACTED if value else value
        return self.text(value) if isinstance(value, str) else value

    def text(self, value: str) -> str:
        """Scrub credentials and assign consistent aliases to public IP literals.

        Args:
            value: Text to sanitize before writing it to the ZIP.

        Returns:
            Sanitized text; personal identifiers may still remain.
        """
        if not self.enabled:
            return value
        value = _ANSI.sub("", value)
        value = _PRIVATE_KEY.sub(REDACTED, value)
        for secret in sorted(self.secrets, key=len, reverse=True):
            value = value.replace(secret, REDACTED)
        value = _AUTH.sub(lambda match: f"{match[1]} {REDACTED}", value)
        value = _COOKIE.sub(lambda match: f"{match[1]}{REDACTED}", value)
        value = _URL_AUTH.sub(lambda match: f"{match[1]}{REDACTED}@", value)
        value = _ASSIGNMENT.sub(lambda match: f"{match[1]}{REDACTED}", value)
        value = _TOKEN.sub(REDACTED, value)
        parts = []
        end = 0
        for match in _IP_LITERAL.finditer(value):
            literal = match[0]
            # Consume URL brackets as a whole to avoid doubled alias brackets.
            candidate = (
                literal[1:-1] if literal.startswith("[") else literal.rstrip(".")
            )
            host, separator, scope = candidate.partition("%")
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                continue
            # Normalize alternate IPv6 spellings and IPv4-mapped IPv6 addresses.
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
                address = address.ipv4_mapped
            if not address.is_global or address.is_multicast:
                continue
            alias = self.public_ips.setdefault(
                str(address), f"[PUBLIC_IP_{len(self.public_ips) + 1}]"
            )
            suffix = separator + scope
            if not literal.startswith("["):
                suffix += literal[len(candidate) :]
            parts.extend((value[end : match.start()], alias + suffix))
            end = match.end()
        parts.append(value[end:])
        return "".join(parts)

    def copy_log(self, source: BinaryIO, target: BinaryIO, limit: int) -> bool:
        """Stream complete text lines, skipping oversized lines and private keys.

        Args:
            source: An already verified regular file, positioned at its start.
            target: Open ZIP entry for redacted text.
            limit: Maximum source bytes to consume, fixed before reading.

        Returns:
            Whether content was omitted to respect line or file limits.
        """
        if not self.enabled:
            remaining = limit
            while remaining:
                chunk = source.read(min(remaining, MAX_LOG_LINE_BYTES))
                if not chunk:
                    break
                target.write(chunk)
                remaining -= len(chunk)
            return False
        truncated = False
        oversized = False
        private_key = False
        remaining = limit
        while remaining:
            line = source.readline(min(remaining, MAX_LOG_LINE_BYTES + 1))
            if not line:
                break
            remaining -= len(line)
            complete = line.endswith(b"\n") or len(line) <= MAX_LOG_LINE_BYTES
            if oversized or not complete:
                oversized = not line.endswith(b"\n")
                truncated = True
                continue
            # Never emit a fragment cut at the export boundary: it could be a token.
            if not remaining and not line.endswith(b"\n") and source.read(1):
                truncated = True
                break
            text = line.decode("utf-8", errors="replace")
            if "-----BEGIN " in text and "PRIVATE KEY-----" in text:
                private_key = True
                target.write((REDACTED + "\n").encode())
            if private_key:
                if "-----END " in text and "PRIVATE KEY-----" in text:
                    private_key = False
                continue
            target.write(self.text(text).encode("utf-8"))
        return truncated


def collect_diagnostics(
    config: dict, core: Any = None, *, redact: bool = True
) -> tuple[dict, DiagnosticRedactor]:
    """Snapshot configuration, plugin status and environment for a log export.

    Args:
        config: Running global configuration.
        core: Running lifecycle, when metadata is available.
        redact: Whether to mask credentials throughout the bundle.

    Returns:
        JSON sections and a redactor seeded from all available credentials.
    """
    redactor = DiagnosticRedactor(enabled=redact)
    redactor.collect(config)
    errors = []
    manager = getattr(core, "astrbot_config_mgr", None)
    profiles = getattr(manager, "confs", {"default": config})
    sections = {
        "config.json": {
            "profiles": {
                name: copy.deepcopy(dict(conf)) for name, conf in profiles.items()
            },
            "profile_metadata": copy.deepcopy(getattr(manager, "abconf_data", {})),
            "routing": copy.deepcopy(
                getattr(
                    getattr(core, "umop_config_router", None), "umop_to_conf_id", {}
                )
            ),
        }
    }
    redactor.collect(sections)
    plugins = []
    plugin_manager = getattr(core, "plugin_manager", None)
    if plugin_manager is not None:
        # Failure to collect plugin credentials aborts the export rather than
        # silently including log text with an incomplete credential dictionary.
        for plugin in plugin_manager.context.get_all_stars():
            redactor.collect(getattr(plugin, "config", None))
            plugins.append(
                {
                    "name": plugin.name,
                    "directory": plugin.root_dir_name,
                    "version": plugin.version,
                    "repo": plugin.repo,
                    "enabled": plugin.activated,
                    "loaded": getattr(plugin, "star_cls", None) is not None,
                    "builtin": plugin.reserved,
                }
            )
    else:
        errors.append(
            {"section": "plugins.json", "error": "Plugin metadata unavailable"}
        )
    sections["plugins.json"] = {
        "plugins": plugins,
        "failed_plugins": copy.deepcopy(
            getattr(plugin_manager, "failed_plugin_dict", {})
        ),
    }
    commit = None
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=get_astrbot_path(),
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    sections["environment.json"] = {
        "astrbot_version": __version__,
        "commit": commit,
        "python_version": platform.python_version(),
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "deployment": "docker" if Path("/.dockerenv").exists() else "unknown",
        "started_at": getattr(core, "start_time", None),
        "collection_errors": errors,
    }
    redactor.collect(sections)
    return sections, redactor
