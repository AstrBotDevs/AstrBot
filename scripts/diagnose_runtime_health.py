from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import io
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OWNER_QQ = "2831304142"
DEFAULT_PROVIDER = "google_gemini_bot/gemini-3.5-flash"
FALLBACK_PROVIDER = "deepseek/deepseek-v4-flash"
FAST_VISION_PROVIDER = "google_gemini_bot/gemini-3.1-flash-lite"
DEEP_VISION_PROVIDER = "google_gemini_bot/gemini-3.5-flash"
DB_PATH = ROOT / "data/data_v4.db"
REQUIRED_DISABLED_PLUGINS = {
    "data.plugins.astrbot_plugin_livingmemory.main",
}
REQUIRED_ENABLED_PLUGINS = {"data.plugins.astrbot_plugin_bilibili.main"}
REQUIRED_DISABLED_API_SEARCH_TOOLS = {
    "web_search_tavily",
    "tavily_extract_web_page",
    "web_search_bocha",
    "web_search_brave",
    "web_search_firecrawl",
    "firecrawl_extract_web_page",
    "web_search_baidu",
    "web_search_exa",
    "exa_get_contents",
}
REQUIRED_BROWSER_TOOLS = {
    "browser_search",
    "browser_open",
    "browser_click",
    "browser_input",
    "browser_scroll",
    "browser_get_link",
}


@dataclass
class Check:
    name: str
    status: str
    detail: str


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_preference(key: str, default: Any) -> Any:
    if not DB_PATH.exists():
        return default
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "select value from preferences where scope=? and scope_id=? and key=?",
            ("global", "global", key),
        ).fetchone()
    if not row:
        return default
    try:
        payload = json.loads(row[0])
    except json.JSONDecodeError:
        return default
    return payload.get("val", default)


def ok(name: str, detail: str) -> Check:
    return Check(name, "OK", detail)


def warn(name: str, detail: str) -> Check:
    return Check(name, "WARN", detail)


def fail(name: str, detail: str) -> Check:
    return Check(name, "FAIL", detail)


def is_port_open(host: str, port: int, timeout: float = 0.75) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def get_process_name(pid: str) -> str:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    if result.returncode != 0 or not result.stdout.strip():
        return ""
    try:
        rows = list(csv.reader(io.StringIO(result.stdout)))
    except csv.Error:
        return ""
    if not rows or not rows[0] or "INFO:" in rows[0][0]:
        return ""
    return rows[0][0]


def get_port_owner_label(port: int) -> str:
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    if result.returncode != 0:
        return ""

    suffixes = (f":{port}", f"]:{port}")
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local_address, state, pid = parts[1], parts[3].upper(), parts[-1]
        if state != "LISTENING" or not local_address.endswith(suffixes):
            continue
        process_name = get_process_name(pid)
        return f" (PID {pid}, {process_name})" if process_name else f" (PID {pid})"
    return ""


def get_listening_port_owner_pid(port: int) -> str:
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    if result.returncode != 0:
        return ""

    suffixes = (f":{port}", f"]:{port}")
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local_address, state, pid = parts[1], parts[3].upper(), parts[-1]
        if state == "LISTENING" and local_address.endswith(suffixes):
            return pid
    return ""


def get_process_start_timestamp(pid: str) -> float | None:
    if not pid:
        return None
    command = (
        "$p=Get-Process -Id "
        + str(pid)
        + " -ErrorAction Stop; "
        + "([DateTimeOffset]$p.StartTime).ToUnixTimeSeconds()"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None
    value = result.stdout.strip().splitlines()[-1:] or [""]
    try:
        return float(value[0])
    except ValueError:
        return None


def get_runtime_owner_start_timestamps() -> list[float]:
    try:
        data = load_json(ROOT / "data/cmd_config.json")
    except Exception:
        return []

    ports: set[int] = set()
    dashboard = data.get("dashboard", {})
    if dashboard.get("enable") is True:
        ports.add(int(dashboard.get("port", 6185) or 6185))
    for platform in data.get("platform", []) or []:
        if platform.get("type") == "aiocqhttp" and platform.get("enable") is True:
            ports.add(int(platform.get("ws_reverse_port", 6199) or 6199))

    pids = {
        pid for pid in (get_listening_port_owner_pid(port) for port in ports) if pid
    }
    return [
        ts
        for ts in (get_process_start_timestamp(pid) for pid in pids)
        if ts is not None
    ]


def resolve_data_path(configured_path: str | None, default_relative_path: str) -> Path:
    raw_path = configured_path or default_relative_path
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return ROOT / "data" / path


def find_system_browser_executable() -> Path | None:
    candidates = [
        os.environ.get("QQTOOLS_BROWSER_EXECUTABLE", ""),
        str(
            Path(os.environ.get("ProgramFiles", ""))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe"
        ),
        str(
            Path(os.environ.get("ProgramFiles(x86)", ""))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe"
        ),
        str(
            Path(os.environ.get("LocalAppData", ""))
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe"
        ),
        str(
            Path(os.environ.get("ProgramFiles", ""))
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe"
        ),
        str(
            Path(os.environ.get("ProgramFiles(x86)", ""))
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe"
        ),
        str(
            Path(os.environ.get("LocalAppData", ""))
            / "Microsoft"
            / "Edge"
            / "Application"
            / "msedge.exe"
        ),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def browser_proxy() -> str:
    return (
        os.environ.get("QQTOOLS_BROWSER_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("ALL_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("http_proxy")
        or os.environ.get("all_proxy")
        or ""
    ).strip()


async def run_browser_smoke(browser_path: Path | None, proxy: str) -> str:
    from playwright.async_api import async_playwright

    launch_kwargs: dict[str, Any] = {"headless": True}
    if browser_path:
        launch_kwargs["executable_path"] = str(browser_path)
    if proxy:
        proxy_url = proxy if "://" in proxy else f"http://{proxy}"
        launch_kwargs["proxy"] = {"server": proxy_url}

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            **launch_kwargs,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
        )
        try:
            page = await browser.new_page()
            await page.goto("about:blank", wait_until="domcontentloaded")
            title = await page.title()
            return title
        finally:
            await browser.close()


def check_core() -> list[Check]:
    path = ROOT / "data/cmd_config.json"
    data = load_json(path)
    provider_settings = data.get("provider_settings", {})
    ltm = data.get("provider_ltm_settings", {})
    provider_sources = data.get("provider_sources", []) or []
    providers = data.get("provider", []) or []
    checks: list[Check] = []

    default_provider = provider_settings.get("default_provider_id")
    checks.append(
        ok("core.default_provider", str(default_provider))
        if default_provider == DEFAULT_PROVIDER
        else fail(
            "core.default_provider",
            f"expected {DEFAULT_PROVIDER}, got {default_provider!r}",
        )
    )

    web_search = provider_settings.get("web_search")
    checks.append(
        ok(
            "core.web_search",
            "built-in web_search is disabled; QQTools browser is used",
        )
        if web_search is False
        else fail(
            "core.web_search",
            f"built-in web_search should be false, got {web_search!r}",
        )
    )
    checks.append(
        ok(
            "core.media_callback",
            "NapCat uses one-time HTTP media sources instead of Windows file paths",
        )
        if data.get("callback_api_base") == "http://host.docker.internal:6185"
        else fail(
            "core.media_callback",
            "callback_api_base must be reachable from the NapCat container",
        )
    )

    log_file_enable = data.get("log_file_enable")
    checks.append(
        ok("core.log_file", "file logging enabled")
        if log_file_enable is True
        else warn(
            "core.log_file",
            f"log_file_enable should be true for troubleshooting, got {log_file_enable!r}",
        )
    )

    persona = provider_settings.get("default_personality")
    checks.append(
        ok("core.persona", str(persona))
        if persona == "atri"
        else fail("core.persona", f"expected atri, got {persona!r}")
    )

    active_reply = (ltm.get("active_reply") or {}).get("enable")
    checks.append(
        ok("core.active_reply", "disabled")
        if active_reply is False
        else fail(
            "core.active_reply",
            f"provider active_reply should be false, got {active_reply!r}",
        )
    )

    platform_settings = data.get("platform_settings", {})
    id_whitelist_enabled = platform_settings.get("enable_id_white_list")
    id_whitelist = platform_settings.get("id_whitelist") or []
    checks.append(
        ok(
            "platform.id_whitelist",
            "empty list means whitelist filtering is skipped by AstrBot",
        )
        if id_whitelist_enabled is True and not id_whitelist
        else ok(
            "platform.id_whitelist",
            f"enabled={id_whitelist_enabled!r}, entries={len(id_whitelist)}",
        )
    )
    rate_limit = platform_settings.get("rate_limit") or {}
    checks.append(
        ok(
            "core.flood_protection",
            "extreme floods are discarded without stalling normal group traffic",
        )
        if int(rate_limit.get("time", 0)) == 10
        and int(rate_limit.get("count", 0)) == 120
        and rate_limit.get("strategy") == "discard"
        else fail(
            "core.flood_protection",
            "expected 120 messages/10 seconds with discard strategy",
        )
    )

    expected_vision = {FAST_VISION_PROVIDER, DEEP_VISION_PROVIDER}
    gemini_enabled = [
        p.get("id")
        for p in providers
        if p.get("id") in expected_vision
        and p.get("provider_type", "chat_completion") == "chat_completion"
        and bool(p.get("enable"))
    ]
    gemini_sources_enabled = [
        s.get("id")
        for s in provider_sources
        if (
            str(s.get("id", "")).startswith("google_gemini")
            or str(s.get("provider", "")) == "google"
        )
        and bool(s.get("enable"))
    ]
    vision_providers = {
        provider.get("id"): provider
        for provider in providers
        if provider.get("id") in {FAST_VISION_PROVIDER, DEEP_VISION_PROVIDER}
    }
    enabled_vision = set(gemini_enabled)
    image_modalities_ok = all(
        "image" in (vision_providers.get(provider_id, {}).get("modalities") or [])
        for provider_id in expected_vision
    )
    checks.append(
        ok(
            "core.vision_provider",
            "Gemini 3.1 Flash-Lite + 3.5 Flash are enabled for layered image input",
        )
        if enabled_vision == expected_vision
        and "google_gemini_bot" in gemini_sources_enabled
        and image_modalities_ok
        else fail(
            "core.vision_provider",
            f"expected enabled {sorted(expected_vision)} with image modality; "
            f"providers={gemini_enabled}, sources={gemini_sources_enabled}, "
            f"modalities_ok={image_modalities_ok}",
        )
    )
    domestic_source = next(
        (
            source
            for source in provider_sources
            if source.get("id") == "google_gemini_bot"
        ),
        None,
    )
    domestic_base = str((domestic_source or {}).get("api_base", "")).rstrip("/")
    domestic_proxy = str((domestic_source or {}).get("proxy", "") or "").strip()
    domestic_hosts = ("apinebula.ai",)
    checks.append(
        ok(
            "core.gemini_domestic_route",
            "google_gemini_bot uses an approved apinebula domestic endpoint directly; proxy remains disabled",
        )
        if domestic_source
        and bool(domestic_source.get("enable"))
        and any(host in domestic_base.lower() for host in domestic_hosts)
        and not domestic_proxy
        else fail(
            "core.gemini_domestic_route",
            f"expected enabled google_gemini_bot on an approved apinebula endpoint without proxy; "
            f"base={domestic_base or '<missing>'}, "
            f"proxy={'set' if domestic_proxy else 'empty'}",
        )
    )
    stt_settings = data.get("provider_stt_settings") or {}
    audio_capable = [
        str(provider.get("id"))
        for provider in providers
        if bool(provider.get("enable"))
        and "audio" in (provider.get("modalities") or [])
    ]
    if bool(stt_settings.get("enable")) and stt_settings.get("provider_id"):
        checks.append(
            ok(
                "core.voice_provider",
                f"STT enabled: {stt_settings['provider_id']}",
            )
        )
    elif audio_capable:
        checks.append(
            ok(
                "core.voice_provider",
                "STT is disabled; audio-capable LLM fallback is available",
            )
        )
    else:
        checks.append(
            fail(
                "core.voice_provider",
                "STT is disabled and no enabled audio-capable provider is available",
            )
        )
    return checks


def check_plugin_configs() -> list[Check]:
    checks: list[Check] = []

    disabled_plugins = set(load_preference("inactivated_plugins", []))
    disabled_tools = set(load_preference("inactivated_llm_tools", []))
    missing_disabled = sorted(REQUIRED_DISABLED_PLUGINS - disabled_plugins)
    wrongly_disabled = sorted(REQUIRED_ENABLED_PLUGINS & disabled_plugins)
    checks.append(
        ok("plugins.runtime_balance", "LivingMemory disabled; Bilibili enabled")
        if not missing_disabled and not wrongly_disabled
        else fail(
            "plugins.runtime_balance",
            f"missing disabled={missing_disabled}; wrongly disabled={wrongly_disabled}",
        )
    )

    bilibili = load_json(ROOT / "data/config/astrbot_plugin_bilibili_config.json")
    parser = load_json(ROOT / "data/config/astrbot_plugin_parser_config.json")
    bili_parser = next(
        (
            item
            for item in parser.get("parsers_template", []) or []
            if item.get("__template_key") == "bilibili"
        ),
        {},
    )
    checks.append(
        ok(
            "plugins.bilibili",
            "BV/card parsing, AI summaries, video extraction, and proxy are enabled",
        )
        if bilibili.get("enable_parse_miniapp") is True
        and bilibili.get("enable_parse_BV") is True
        and bilibili.get("enable_ai_summary") is True
        and bilibili.get("proxy") == "http://127.0.0.1:7897"
        and bili_parser.get("enable") is True
        and bili_parser.get("use_proxy") is True
        and parser.get("proxy") == "http://127.0.0.1:7897"
        else fail("plugins.bilibili", "Bilibili plugin or parser configuration drift")
    )
    ffmpeg_candidates: list[str] = []
    resolved_ffmpeg = shutil.which("ffmpeg")
    if resolved_ffmpeg:
        ffmpeg_candidates.append(resolved_ffmpeg)
    if not ffmpeg_candidates:
        winget_ffmpeg = (
            Path(os.environ.get("LOCALAPPDATA", ""))
            / "Microsoft"
            / "WinGet"
            / "Links"
            / "ffmpeg.exe"
        )
        try:
            if winget_ffmpeg.is_file():
                ffmpeg_candidates.append(str(winget_ffmpeg))
        except PermissionError:
            ffmpeg_candidates.append(str(winget_ffmpeg))
    if not ffmpeg_candidates:
        try:
            import imageio_ffmpeg

            bundled_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            if bundled_ffmpeg:
                ffmpeg_candidates.append(str(bundled_ffmpeg))
        except (ImportError, OSError, RuntimeError):
            pass
    ffmpeg_path = ""
    for candidate in ffmpeg_candidates:
        try:
            probe = subprocess.run(
                [candidate, "-version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0:
            ffmpeg_path = candidate
            break
    if not ffmpeg_path:
        try:
            import imageio_ffmpeg

            bundled_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            if bundled_ffmpeg:
                probe = subprocess.run(
                    [bundled_ffmpeg, "-version"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=3,
                    check=False,
                )
                if probe.returncode == 0:
                    ffmpeg_path = str(bundled_ffmpeg)
        except (ImportError, OSError, subprocess.SubprocessError, RuntimeError):
            pass
    checks.append(
        ok("runtime.ffmpeg", ffmpeg_path)
        if ffmpeg_path
        else warn(
            "runtime.ffmpeg",
            "ffmpeg is unavailable; music/video delivery is disabled until a runnable binary is installed",
        )
    )

    missing_disabled_tools = sorted(REQUIRED_DISABLED_API_SEARCH_TOOLS - disabled_tools)
    checks.append(
        ok(
            "tools.api_search_disabled",
            "legacy Tavily tools are disabled; controlled search backends are used",
        )
        if not missing_disabled_tools
        else fail(
            "tools.api_search_disabled",
            f"API-key web search tools still active: {missing_disabled_tools}",
        )
    )
    disabled_browser_tools = sorted(REQUIRED_BROWSER_TOOLS & disabled_tools)
    checks.append(
        ok("tools.browser_available", "required browser tools are not disabled")
        if not disabled_browser_tools
        else fail(
            "tools.browser_available",
            f"required browser tools are disabled: {disabled_browser_tools}",
        )
    )

    spectrecore = load_json(ROOT / "data/config/spectrecore_config.json")
    checks.append(
        ok("spectrecore.main_reply", "tools enabled, groups/private enabled")
        if spectrecore.get("use_func_tool") is True
        and spectrecore.get("enable_all_groups") is True
        and spectrecore.get("enabled_private") is True
        else fail(
            "spectrecore.main_reply",
            "SpectreCore should be the main reply plugin with tools enabled",
        )
    )

    semantic_router_config = load_json(
        ROOT / "data/config/astrbot_plugin_semantic_router_config.json"
    )
    checks.append(
        ok(
            "semantic_router.realtime_search",
            "AnySearch evidence is primary with deterministic QQTools fallback",
        )
        if (ROOT / "data/plugins/astrbot_plugin_anysearch/main.py").is_file()
        and semantic_router_config.get("anysearch_enabled") is True
        and semantic_router_config.get("direct_search_enabled") is True
        and semantic_router_config.get("integrated_search_answer_enabled") is True
        and semantic_router_config.get("knowledge_auto_stage_search_enabled") is True
        else fail(
            "semantic_router.realtime_search",
            "AnySearch routing, deterministic search, or controlled knowledge staging drifted",
        )
    )
    checks.append(
        ok(
            "semantic_router.adaptive_mailbox",
            "adaptive mailbox capacity, coalescing, and FAST reserve are enabled",
        )
        if semantic_router_config.get("adaptive_mailbox_enabled") is True
        and int(semantic_router_config.get("mailbox_global_capacity", 0)) == 32
        and int(semantic_router_config.get("mailbox_session_capacity", 0)) == 6
        and float(semantic_router_config.get("fragment_quiet_window_seconds", 0)) == 1.2
        and float(semantic_router_config.get("fragment_hard_window_seconds", 0)) == 4.0
        and int(semantic_router_config.get("mailbox_max_merge_count", 0)) == 5
        and int(
            semantic_router_config.get("control_plane_fast_reserved_concurrency", 0)
        )
        == 1
        else fail(
            "semantic_router.adaptive_mailbox",
            "adaptive mailbox configuration is missing or has drifted",
        )
    )
    checks.append(
        ok(
            "semantic_router.semantic_planner",
            "intent is classified by a bounded fast model before search/memory execution",
        )
        if semantic_router_config.get("semantic_planner_enabled") is True
        and semantic_router_config.get("context_on_wake_required") is True
        and float(semantic_router_config.get("semantic_planner_timeout_seconds", 0))
        <= 4.0
        and "_plan_semantic_intent"
        in (ROOT / "data/plugins/astrbot_plugin_semantic_router/main.py").read_text(
            encoding="utf-8-sig"
        )
        else fail(
            "semantic_router.semantic_planner",
            "semantic planner or mandatory wake context configuration is missing",
        )
    )

    qqtools = load_json(ROOT / "data/config/astrbot_plugin_qq_tools_config.json")
    browser = qqtools.get("browser_config", {})
    permission = qqtools.get("tool_permission", {})
    allow_users = [str(user) for user in permission.get("tool_allow_users", [])]
    admin_only_tools = permission.get("admin_only_tools", [])
    checks.append(
        ok(
            "qqtools.browser",
            "browser reads are available; interactive mutations use Agent risk approval",
        )
        if browser.get("browser") is True
        and OWNER_QQ in allow_users
        and "browser_*" not in admin_only_tools
        and "browser_click*" not in admin_only_tools
        and "browser_input" not in admin_only_tools
        and "browser_send_image" in admin_only_tools
        else fail(
            "qqtools.browser",
            "QQTools browser read/write permissions are not safely separated",
        )
    )
    office_config = load_json(
        ROOT / "data/config/astrbot_plugin_office_assistant_config.json"
    )
    office_trigger = office_config.get("trigger_settings", {})
    office_permission = office_config.get("permission_settings", {})
    office_read = office_config.get("read_settings", {})
    checks.append(
        ok(
            "office_assistant.restricted",
            "Office tools are owner-only, mention-gated, workspace-scoped, and built",
        )
        if (ROOT / "data/plugins/astrbot_plugin_office_assistant/main.py").is_file()
        and (
            ROOT
            / "data/plugins/astrbot_plugin_office_assistant/word_renderer_js/dist/cli.js"
        ).is_file()
        and office_trigger.get("enable_features_in_group") is True
        and office_trigger.get("require_at_in_group") is True
        and office_trigger.get("allow_local_excel_script") is False
        and office_permission.get("allow_all_users") is False
        and OWNER_QQ
        in {str(item) for item in office_permission.get("whitelist_users", [])}
        and office_read.get("allow_external_input_files") is False
        else fail(
            "office_assistant.restricted",
            "Office plugin build or owner/workspace restrictions are incomplete",
        )
    )
    mcp_config = load_json(ROOT / "data/mcp_server.json")
    anysearch_mcp = mcp_config.get("mcpServers", {}).get(
        "anysearch-readonly-fallback", {}
    )
    mcp_shape_ok = (
        anysearch_mcp.get("active") is True
        and anysearch_mcp.get("url") == "https://api.anysearch.com/mcp"
        and anysearch_mcp.get("transport") == "streamable_http"
        and anysearch_mcp.get("tool_name_prefix") == "mcp_anysearch_"
        and not anysearch_mcp.get("headers")
    )
    unavailable_mcp_tools: list[str] = []
    capability_db = (
        ROOT / "data/plugin_data/astrbot_plugin_semantic_router/agent_control.db"
    )
    if capability_db.exists():
        try:
            with sqlite3.connect(capability_db) as conn:
                rows = conn.execute(
                    "select name from capability_catalog "
                    "where status='unavailable' and name like 'mcp_anysearch_%'"
                ).fetchall()
            unavailable_mcp_tools = [str(row[0]) for row in rows]
        except sqlite3.Error:
            unavailable_mcp_tools = []
    if not mcp_shape_ok:
        checks.append(
            fail(
                "mcp.anysearch_fallback",
                "AnySearch MCP fallback is missing, duplicated, or contains embedded credentials",
            )
        )
    elif unavailable_mcp_tools:
        checks.append(
            warn(
                "mcp.anysearch_fallback",
                "MCP endpoint is unavailable; AnySearch plugin remains the primary path "
                f"({len(unavailable_mcp_tools)} fallback tools unavailable)",
            )
        )
    else:
        checks.append(
            ok(
                "mcp.anysearch_fallback",
                "anonymous read-only AnySearch MCP fallback uses an isolated tool prefix",
            )
        )

    angel = load_json(ROOT / "data/config/astrbot_plugin_angel_heart_config.json")
    angel_access = angel.get("access_control", {})
    angel_wake = angel.get("wake_interaction", {})
    checks.append(
        ok(
            "angel_heart.passive_gate",
            "passive takeover is gated while explicit wake always replies",
        )
        if angel_access.get("whitelist_enabled") is True
        and angel_access.get("chat_ids") == []
        and angel_access.get("group_chat_enhancement") is False
        and angel_wake.get("force_reply_when_summoned") is True
        and angel_wake.get("reply_even_not_questioned") is True
        else fail("angel_heart.passive_gate", "AngelHeart is not fully gated")
    )
    angel_identity = (angel.get("personality") or {}).get("ai_self_identity", "")
    checks.append(
        ok("persona.angel_heart", "ATRI identity and wake aliases aligned")
        if "亚托莉" in angel_identity
        and "修理工" in angel_identity
        and "香草" not in angel_identity
        and str(angel_wake.get("alias", "")).startswith("亚托莉|")
        else fail("persona.angel_heart", "AngelHeart still has persona drift")
    )

    private = load_json(
        ROOT / "data/config/astrbot_plugin_private_companion_config.json"
    )
    checks.append(
        ok("private_companion.mode", "proactive-only auxiliary mode")
        if private.get("enabled") is True
        and (private.get("basic_config") or {}).get("enable_proactive_only_mode")
        is True
        and (private.get("group_observation_config") or {}).get(
            "enable_group_companion"
        )
        is False
        and (private.get("humanized_state_config") or {}).get("inject_passive_states")
        is False
        else fail(
            "private_companion.mode",
            "Private Companion should be proactive-only and non-passive",
        )
    )
    private_basic = private.get("basic_config") or {}
    checks.append(
        ok(
            "persona.private_companion",
            "owner uses direct you/I address; repairer remains a third-person relation",
        )
        if private_basic.get("bot_name") == "亚托莉"
        and private_basic.get("plugin_specific_persona_id") == "atri"
        and private_basic.get("target_user_ids") == [OWNER_QQ]
        and private_basic.get("private_user_aliases") == f"你={OWNER_QQ}"
        and private.get("enable_livingmemory_integration") is False
        and (private.get("external_memory_config") or {}).get(
            "enable_livingmemory_integration"
        )
        is False
        else fail(
            "persona.private_companion",
            "owner address and repairer relation are not aligned",
        )
    )
    companion_store_path = (
        ROOT / "data/plugin_data/astrbot_plugin_private_companion/companions.json"
    )
    companion_store = (
        load_json(companion_store_path) if companion_store_path.exists() else {}
    )
    companion_users = companion_store.get("users") or {}
    owner_keys = {
        str(user_id)
        for user_id, record in companion_users.items()
        if isinstance(record, dict) and record.get("relationship_role") == "owner"
    }
    checks.append(
        ok("memory.private_identity", "private memory owner is keyed by stable QQ ID")
        if not companion_store_path.exists()
        or not companion_users
        or (OWNER_QQ in owner_keys and owner_keys <= {OWNER_QQ})
        else fail(
            "memory.private_identity",
            f"private memory owner record uses display alias(es): {sorted(owner_keys)}",
        )
    )

    wakepro = load_json(ROOT / "data/config/astrbot_plugin_wakepro_config.json")
    pipeline = wakepro.get("pipeline", {})
    contextual_wake = wakepro.get("wake", {})
    checks.append(
        ok(
            "wakepro.contextual_followup",
            "mention plus low-cost contextual follow-up pipeline",
        )
        if pipeline.get("steps")
        == ["mention(\u63d0\u53ca\u5524\u9192)", "wake(\u667a\u80fd\u5524\u9192)"]
        and pipeline.get("blacklist_steps") == []
        and float(contextual_wake.get("prolong", 0)) == 60.0
        and float(contextual_wake.get("similar", 1)) == 0.35
        and float(contextual_wake.get("ask", 0)) == 1.0
        and float(contextual_wake.get("bored", 0)) == 1.0
        and float(contextual_wake.get("interest", 0)) == 1.0
        and float(contextual_wake.get("prob", 1)) == 0.0
        else fail(
            "wakepro.contextual_followup",
            "WakePro should allow only mention and controlled contextual follow-up",
        )
    )

    meme = load_json(ROOT / "data/config/meme_manager_config.json")
    checks.append(
        ok("meme_manager.frequency", "low-frequency stickers")
        if meme.get("emotion_llm_provider_id") == FALLBACK_PROVIDER
        and int(meme.get("max_emotions_per_message", 0)) <= 1
        and int(meme.get("emotions_probability", 100)) <= 35
        else warn("meme_manager.frequency", "sticker frequency may be too high")
    )

    self_learning = load_json(
        ROOT / "data/config/astrbot_plugin_self_learning_config.json"
    )
    basic = self_learning.get("Self_Learning_Basic", {})
    ml = self_learning.get("Machine_Learning_Settings", {})
    affection = self_learning.get("Affection_System_Settings", {})
    mood = self_learning.get("Mood_System_Settings", {})
    social = self_learning.get("Social_Context_Settings", {})
    maibot = self_learning.get("MaiBot_Enhancement", {})
    integration = self_learning.get("Integration_Settings", {})
    runtime_internal = self_learning.get("Runtime_Internal_Settings", {})
    expected_on_flags = {
        "enable_message_capture": basic.get("enable_message_capture"),
        "enable_auto_learning": basic.get("enable_auto_learning"),
        "enable_affection_system": affection.get("enable_affection_system"),
        "enable_daily_mood": mood.get("enable_daily_mood"),
        "enable_social_context_injection": social.get(
            "enable_social_context_injection"
        ),
        "include_affection_info": social.get("include_affection_info"),
        "enable_expression_patterns": maibot.get("enable_expression_patterns"),
        "enable_llm_hooks": runtime_internal.get("enable_llm_hooks"),
    }
    expected_batch_flags = {
        "enable_jargon_learning": basic.get("enable_jargon_learning"),
        "enable_style_learning": basic.get("enable_style_learning"),
        "enable_expression_user_scope": maibot.get("enable_expression_user_scope"),
    }
    off_slow_flags = {
        "enable_realtime_learning": basic.get("enable_realtime_learning"),
        "enable_realtime_expression_learning": maibot.get(
            "enable_realtime_expression_learning"
        ),
        "enable_ml_analysis": ml.get("enable_ml_analysis"),
        "enable_memory_graph": maibot.get("enable_memory_graph"),
        "enable_knowledge_graph": maibot.get("enable_knowledge_graph"),
        "delegate_memory_to_livingmemory": integration.get(
            "delegate_memory_to_livingmemory"
        ),
    }
    disabled_expected = [
        key for key, value in expected_on_flags.items() if value is not True
    ]
    disabled_batch_flags = [
        key for key, value in expected_batch_flags.items() if value is not True
    ]
    enabled_slow_flags = [key for key, value in off_slow_flags.items() if value is True]
    hook_timeout = float(runtime_internal.get("llm_hook_context_timeout", 999) or 999)
    checks.append(
        ok(
            "self_learning.balanced",
            "capture and group-scoped batch social learning enabled; realtime slow paths disabled",
        )
        if not disabled_expected
        and not disabled_batch_flags
        and not enabled_slow_flags
        and hook_timeout <= 1.5
        else fail(
            "self_learning.balanced",
            f"disabled expected flags={disabled_expected}; disabled batch flags={disabled_batch_flags}; enabled slow flags={enabled_slow_flags}; hook_timeout={hook_timeout}",
        )
    )

    livingmemory = load_json(
        ROOT / "data/config/astrbot_plugin_livingmemory_config.json"
    )
    embedding_provider = (livingmemory.get("provider_settings") or {}).get(
        "embedding_provider_id"
    )
    checks.append(
        ok(
            "livingmemory.disabled_or_ready",
            "plugin disabled and no embedding wait should run",
        )
        if "data.plugins.astrbot_plugin_livingmemory.main" in disabled_plugins
        else fail(
            "livingmemory.disabled_or_ready",
            f"plugin is active; embedding provider={embedding_provider!r}",
        )
    )
    return checks


def check_browser_environment(smoke: bool = False) -> list[Check]:
    checks: list[Check] = []
    qqtools = load_json(ROOT / "data/config/astrbot_plugin_qq_tools_config.json")
    browser_config = qqtools.get("browser_config", {})

    checks.append(
        ok("browser.config", "QQTools browser is enabled")
        if browser_config.get("browser") is True
        and browser_config.get("auto_install_browser_deps") is False
        else fail(
            "browser.config",
            "QQTools browser must be enabled and auto_install_browser_deps should remain false",
        )
    )

    mark_script = ROOT / "data/plugins/astrbot_plugin_qq_tools/mark_script.js"
    checks.append(
        ok("browser.mark_script", str(mark_script))
        if mark_script.is_file()
        else fail("browser.mark_script", f"missing {mark_script}")
    )

    playwright_spec = importlib.util.find_spec("playwright")
    checks.append(
        ok("browser.playwright", "playwright is importable")
        if playwright_spec is not None
        else fail(
            "browser.playwright",
            "playwright is not importable in the current Python environment",
        )
    )

    browser_path = find_system_browser_executable()
    checks.append(
        ok("browser.executable", str(browser_path))
        if browser_path
        else fail("browser.executable", "Chrome or Edge executable was not found")
    )

    proxy = browser_proxy()
    checks.append(
        ok("browser.proxy", proxy)
        if proxy
        else warn("browser.proxy", "no proxy environment is set for browser tools")
    )

    if smoke:
        if playwright_spec is None:
            checks.append(
                fail("browser.smoke", "skipped because playwright is not importable")
            )
        else:
            try:
                title = asyncio.run(run_browser_smoke(browser_path, proxy))
                checks.append(
                    ok(
                        "browser.smoke",
                        f"headless browser launched successfully; title={title!r}",
                    )
                )
            except Exception as e:
                checks.append(
                    fail("browser.smoke", f"headless browser launch failed: {e}")
                )

    return checks


def check_runtime_ports() -> list[Check]:
    data = load_json(ROOT / "data/cmd_config.json")
    checks: list[Check] = []
    any_runtime_port_open = False
    runtime_owner_pids: set[str] = set()

    dashboard = data.get("dashboard", {})
    dashboard_port = int(dashboard.get("port", 6185) or 6185)
    dashboard_open = is_port_open("127.0.0.1", dashboard_port)
    any_runtime_port_open = any_runtime_port_open or dashboard_open
    if dashboard_open:
        owner_pid = get_listening_port_owner_pid(dashboard_port)
        if owner_pid:
            runtime_owner_pids.add(owner_pid)
    checks.append(
        ok(
            "runtime.dashboard_port",
            f"127.0.0.1:{dashboard_port} is listening{get_port_owner_label(dashboard_port)}",
        )
        if dashboard_open
        else warn(
            "runtime.dashboard_port",
            f"127.0.0.1:{dashboard_port} is not listening; AstrBot may be stopped",
        )
    )

    for platform in data.get("platform", []) or []:
        if platform.get("type") != "aiocqhttp" or platform.get("enable") is not True:
            continue
        port = int(platform.get("ws_reverse_port", 6199) or 6199)
        ws_open = is_port_open("127.0.0.1", port)
        any_runtime_port_open = any_runtime_port_open or ws_open
        if ws_open:
            owner_pid = get_listening_port_owner_pid(port)
            if owner_pid:
                runtime_owner_pids.add(owner_pid)
        checks.append(
            ok(
                "runtime.onebot_ws_port",
                f"127.0.0.1:{port} is listening for NapCat reverse WebSocket{get_port_owner_label(port)}",
            )
            if ws_open
            else warn(
                "runtime.onebot_ws_port",
                f"127.0.0.1:{port} is not listening; NapCat cannot connect until AstrBot starts",
            )
        )

    log_path = resolve_data_path(data.get("log_file_path"), "logs/astrbot.log")
    if any_runtime_port_open and data.get("log_file_enable") is True:
        if log_path.exists():
            age_seconds = datetime.now().timestamp() - log_path.stat().st_mtime
            checks.append(
                ok(
                    "runtime.file_log",
                    f"{log_path} updated {int(age_seconds)} seconds ago",
                )
                if age_seconds <= 3600
                else warn(
                    "runtime.file_log",
                    f"{log_path} exists but has not updated in {int(age_seconds // 60)} minutes",
                )
            )
        else:
            checks.append(
                warn(
                    "runtime.file_log",
                    f"{log_path} does not exist yet; restart AstrBot to load file logging config",
                )
            )

    watched_files = [
        ROOT / "astrbot/core/platform/sources/aiocqhttp/aiocqhttp_platform_adapter.py",
        ROOT / "astrbot/core/agent/tool.py",
        ROOT / "astrbot/core/agent/tool_gateway.py",
        ROOT / "astrbot/core/agent/model_gateway.py",
        ROOT / "astrbot/core/agent/job_manager.py",
        ROOT / "astrbot/core/agent/evidence_store.py",
        ROOT / "astrbot/core/agent/stream_controller.py",
        ROOT / "astrbot/core/astr_agent_run_util.py",
        ROOT / "astrbot/core/agent/runners/tool_loop_agent_runner.py",
        ROOT / "data/plugins/astrbot_plugin_semantic_router/main.py",
        ROOT / "data/plugins/astrbot_plugin_semantic_router/control_plane.py",
        ROOT / "data/plugins/astrbot_plugin_listen_music/agent_capabilities.yaml",
        ROOT / "data/plugins/astrbot_plugin_image_processor/main.py",
        ROOT / "data/plugins/astrbot_plugin_qq_tools/main.py",
        ROOT / "data/plugins/astrbot_plugin_qq_tools/tools/browser.py",
        ROOT / "data/plugins/spectrecore/utils/llm_utils.py",
    ]
    newest_file = max(
        (path for path in watched_files if path.exists()),
        key=lambda path: path.stat().st_mtime,
        default=None,
    )
    owner_starts = [
        ts
        for ts in (get_process_start_timestamp(pid) for pid in runtime_owner_pids)
        if ts is not None
    ]
    if newest_file and owner_starts:
        oldest_owner_start = min(owner_starts)
        if newest_file.stat().st_mtime > oldest_owner_start + 2:
            changed_at = datetime.fromtimestamp(newest_file.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            started_at = datetime.fromtimestamp(oldest_owner_start).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            checks.append(
                warn(
                    "runtime.restart_needed",
                    f"{newest_file} changed at {changed_at}, after runtime PID start {started_at}; restart AstrBot to load it",
                )
            )
        else:
            checks.append(
                ok(
                    "runtime.restart_needed",
                    "running process is newer than watched plugin files",
                )
            )
    elif any_runtime_port_open:
        checks.append(
            warn(
                "runtime.restart_needed",
                "could not compare process start time with watched plugin files",
            )
        )
    return checks


def check_code_guards() -> list[Check]:
    checks: list[Check] = []
    tool_gateway_path = ROOT / "astrbot/core/agent/tool_gateway.py"
    evidence_store_path = ROOT / "astrbot/core/agent/evidence_store.py"
    tool_gateway = (
        tool_gateway_path.read_text(encoding="utf-8-sig")
        if tool_gateway_path.exists()
        else ""
    )
    evidence_store = (
        evidence_store_path.read_text(encoding="utf-8-sig")
        if evidence_store_path.exists()
        else ""
    )
    runner_source = (
        ROOT / "astrbot/core/agent/runners/tool_loop_agent_runner.py"
    ).read_text(encoding="utf-8-sig")
    semantic_router_source = (
        ROOT / "data/plugins/astrbot_plugin_semantic_router/main.py"
    ).read_text(encoding="utf-8-sig")
    control_plane_source = (
        ROOT / "data/plugins/astrbot_plugin_semantic_router/control_plane.py"
    ).read_text(encoding="utf-8-sig")
    checks.append(
        ok(
            "code.unified_tool_gateway",
            "ToolGateway validates schemas, normalizes outcomes, and owns resource leases",
        )
        if "class ToolGateway" in tool_gateway
        and "validate_arguments" in tool_gateway
        and "async def invoke" in tool_gateway
        and "ToolResourceScheduler" in tool_gateway
        and "ToolGateway.invoke(" in runner_source
        and semantic_router_source.count("ToolGateway.invoke(") >= 2
        else fail(
            "code.unified_tool_gateway",
            "unified ToolGateway or bounded resource scheduler is missing",
        )
    )
    checks.append(
        ok(
            "code.agent_evidence_chain",
            "Agent runs, tool attempts, and hash-only evidence are persisted",
        )
        if "class AgentEvidenceStore" in evidence_store
        and "agent_runs" in evidence_store
        and "tool_attempts" in evidence_store
        and "evidence_records" in evidence_store
        and "trace_id" in control_plane_source
        and "audit_decision" in control_plane_source
        else fail(
            "code.agent_evidence_chain",
            "Agent evidence store or decision-to-trace link is missing",
        )
    )
    checks.append(
        ok(
            "code.shadow_acceptance_telemetry",
            "plan candidates, trace-linked tool calls, and delivery outcomes are audited",
        )
        if "candidate_tools" in control_plane_source
        and "tool_required" in control_plane_source
        and "trace_id TEXT NOT NULL DEFAULT ''" in control_plane_source
        and "message_delivery_audit" in control_plane_source
        and "audit_message_delivery" in control_plane_source
        and "audit_response_candidate" in semantic_router_source
        else fail(
            "code.shadow_acceptance_telemetry",
            "shadow acceptance telemetry is incomplete",
        )
    )
    pipeline_context = (ROOT / "astrbot/core/pipeline/context_utils.py").read_text(
        encoding="utf-8-sig"
    )
    checks.append(
        ok(
            "code.after_send_cleanup",
            "all post-send cleanup hooks run even when an event is already stopped",
        )
        if "hook_type != EventType.OnAfterMessageSentEvent" in pipeline_context
        else fail(
            "code.after_send_cleanup",
            "a stopped result can prevent later post-send lock cleanup hooks",
        )
    )
    aiocqhttp_adapter = (
        ROOT / "astrbot/core/platform/sources/aiocqhttp/aiocqhttp_platform_adapter.py"
    ).read_text(encoding="utf-8-sig")
    checks.append(
        ok(
            "code.aiocqhttp_mface_image",
            "QQ store emojis are preserved as standard image components",
        )
        if 'elif t in {"mface", "marketface"}' in aiocqhttp_adapter
        and "abm.message.append(Image(file=image_url, url=image_url))"
        in aiocqhttp_adapter
        and 'elif t == "mface":\n                continue' not in aiocqhttp_adapter
        else fail(
            "code.aiocqhttp_mface_image",
            "QQ store emojis can be silently dropped before image understanding",
        )
    )
    qqtools_main = (ROOT / "data/plugins/astrbot_plugin_qq_tools/main.py").read_text(
        encoding="utf-8-sig"
    )
    qqtools_browser = (
        ROOT / "data/plugins/astrbot_plugin_qq_tools/tools/browser.py"
    ).read_text(encoding="utf-8-sig")
    checks.append(
        ok(
            "code.qqtools_browser_search",
            "browser_search is implemented and registered",
        )
        if "class BrowserSearchTool" in qqtools_browser
        and "BrowserSearchTool" in qqtools_main
        and '"browser_search"' in qqtools_main
        else fail(
            "code.qqtools_browser_search",
            "browser_search tool is missing or not registered",
        )
    )
    semantic_router = (
        ROOT / "data/plugins/astrbot_plugin_semantic_router/main.py"
    ).read_text(encoding="utf-8-sig")
    checks.append(
        ok(
            "code.semantic_router_private_wake",
            "private messages materialize wake state before ProcessStage",
        )
        if "event.is_private_chat()" in semantic_router
        and "self.route_private_without_wake" in semantic_router
        and "event.is_at_or_wake_command = True" in semantic_router
        else fail(
            "code.semantic_router_private_wake",
            "private messages may be routed but skipped by ProcessStage",
        )
    )
    skill_manager = (ROOT / "astrbot/core/skills/skill_manager.py").read_text(
        encoding="utf-8-sig"
    )
    main_agent = (ROOT / "astrbot/core/astr_main_agent.py").read_text(
        encoding="utf-8-sig"
    )
    iris_processor = (
        ROOT
        / "data/plugins/astrbot_plugin_iris_memory/iris_memory/processing/message_processor.py"
    ).read_text(encoding="utf-8-sig")
    checks.append(
        ok(
            "code.identity_memory_boundaries",
            "persona, Skills, Iris memory, and companion context cannot grant permissions",
        )
        if "Skill trust boundary" in skill_manager
        and "<astrbot_runtime_boundaries>" in main_agent
        and "<iris_memory_boundary>" in iris_processor
        and "<private_companion_boundary>"
        in (ROOT / "data/plugins/astrbot_plugin_private_companion/main.py").read_text(
            encoding="utf-8-sig"
        )
        else fail(
            "code.identity_memory_boundaries",
            "untrusted persona/Skill/memory context is missing an explicit boundary",
        )
    )
    checks.append(
        ok(
            "code.iris_persona_scope",
            "Iris memory uses configured persona scope and caches one-turn retrieval",
        )
        if "get_persona_id_for_query" in iris_processor
        and "get_persona_id_for_storage" in iris_processor
        and "iris_memory_context_ready" in iris_processor
        and 'where_clause["persona_id"] = persona_id'
        in (
            ROOT
            / "data/plugins/astrbot_plugin_iris_memory/iris_memory/web/repositories/memory_repo.py"
        ).read_text(encoding="utf-8-sig")
        else fail(
            "code.iris_persona_scope",
            "Iris memory may use a null persona scope or repeat retrieval on tool-loop turns",
        )
    )
    checks.append(
        ok(
            "code.skill_metadata_boundary",
            "Skill frontmatter is sanitized before prompt injection",
        )
        if "def _sanitize_prompt_description" in skill_manager
        and "description = _sanitize_prompt_description(skill.description"
        in skill_manager
        and "untrusted task data" in skill_manager
        else fail(
            "code.skill_metadata_boundary",
            "Skill metadata can inject unsanitized instructions into the Agent prompt",
        )
    )
    image_processor = (
        ROOT / "data/plugins/astrbot_plugin_image_processor/main.py"
    ).read_text(encoding="utf-8-sig")
    checks.append(
        ok(
            "code.image_processor_timeout_fallback",
            "vision timeout reuses preflight evidence without a second OCR lock",
        )
        if 'category="preflight_fallback"' in image_processor
        and 'model_id="local/preflight"' in image_processor
        and "async with self._semaphore:" in image_processor
        and "async with session_lock, self._semaphore:" not in image_processor
        and "image context exceeded hard deadline" in semantic_router
        else fail(
            "code.image_processor_timeout_fallback",
            "vision timeout can repeat OCR or retain a conversation lock",
        )
    )
    checks.append(
        ok(
            "code.semantic_router_image_priority",
            "resolved images take priority over generic search phrases",
        )
        if "if image_requested:" in semantic_router
        and 'query = ""' in semantic_router
        and 'event.set_extra("semantic_router_image_requested", True)'
        in semantic_router
        and "visual evidence indicates that meme provenance" in semantic_router
        else fail(
            "code.semantic_router_image_priority",
            "quoted image questions may be diverted into web search before vision",
        )
    )
    checks.append(
        ok(
            "code.semantic_router_recent_image_bridge",
            "image-only events are cached before WakePro and restored for follow-ups",
        )
        if "priority=100000" in semantic_router
        and "async def capture_recent_images" in semantic_router
        and "semantic_router_recent_image_attached" in semantic_router
        and "semantic_router_recent_image_paths" in semantic_router
        and "Comp.Image.fromFileSystem(path)" in semantic_router
        and "def _references_recent_image" in semantic_router
        and '"我上面发图片"' in semantic_router
        else fail(
            "code.semantic_router_recent_image_bridge",
            "separate image and follow-up text events can lose visual context",
        )
    )
    checks.append(
        ok(
            "code.semantic_router_wake_context_snapshot",
            "name wakes materialize scoped context before downstream handlers",
        )
        if '"semantic_router_context_snapshot"' in semantic_router
        and "semantic_router_context_required" in semantic_router
        and "isinstance(item, Comp.Reply)" in semantic_router
        and 'text = "[图片]"' in semantic_router
        else fail(
            "code.semantic_router_wake_context_snapshot",
            "wake context can be lost when a downstream handler short-circuits",
        )
    )
    checks.append(
        ok(
            "code.image_processor_unstructured_response",
            "restored image paths and plain-text Gemini output remain usable",
        )
        if '"social_intent": raw[:1600]' in image_processor
        and '"confidence": 0.75' in image_processor
        and 'get_extra("semantic_router_recent_image_paths", [])' in image_processor
        and 'message_obj = getattr(event, "message_obj", None)' in image_processor
        else fail(
            "code.image_processor_unstructured_response",
            "non-JSON vision responses or restored QQ image paths can be discarded",
        )
    )
    main_agent_source = (ROOT / "astrbot/core/astr_main_agent.py").read_text(
        encoding="utf-8-sig"
    )
    checks.append(
        ok(
            "code.main_agent_dynamic_vision_fallback",
            "image requests discover active Gemini vision providers from Provider Manager",
        )
        if "available_providers: list[Provider] | None = None" in main_agent_source
        and "plugin_context.get_all_providers()" in main_agent_source
        and 'startswith("google_gemini_bot/")' in main_agent_source
        else fail(
            "code.main_agent_dynamic_vision_fallback",
            "image requests are limited to text fallback_chat_models",
        )
    )
    antiprompt_source = (ROOT / "data/plugins/antipromptinjector/main.py").read_text(
        encoding="utf-8-sig"
    )
    antiprompt_config = load_json(ROOT / "data/config/antipromptinjector_config.json")
    checks.append(
        ok(
            "code.antiprompt_admin_guard",
            "administrators cannot be auto-blacklisted by persona heuristics",
        )
        if "if event.is_admin():" in antiprompt_source
        and "removed administrator" in antiprompt_source
        and "2831304142" not in (antiprompt_config.get("blacklist") or {})
        else fail(
            "code.antiprompt_admin_guard",
            "a false-positive anti-prompt heuristic can stop the owner response path",
        )
    )
    checks.append(
        ok(
            "code.semantic_router_bounded_search",
            "meme searches use QQTools first and all evidence retrieval has a hard deadline",
        )
        if "self._fetch_search_result(event, query), timeout=15.0" in semantic_router
        and '"browser_search",' in semantic_router
        and "timeout=10," in semantic_router
        and "self._fetch_search_candidate(kind, engine, url), timeout=4.0"
        in semantic_router
        else fail(
            "code.semantic_router_bounded_search",
            "search fallback can bypass QQTools or retain a conversation indefinitely",
        )
    )
    angel_front_desk = (
        ROOT / "data/plugins/astrbot_plugin_angel_heart/roles/front_desk.py"
    ).read_text(encoding="utf-8-sig")
    checks.append(
        ok(
            "code.angel_heart_control_plane_bypass",
            "admitted FAST and WORK requests skip AngelHeart's second queue",
        )
        if 'event.get_extra("agent_mailbox_class", "")' in angel_front_desk
        and '"angelheart_control_plane_bypass"' in angel_front_desk
        and '{"FAST", "WORK", "CRITICAL"}' in angel_front_desk
        else fail(
            "code.angel_heart_control_plane_bypass",
            "control-plane requests can be delayed again by AngelHeart detention",
        )
    )
    checks.append(
        ok(
            "code.semantic_router_tool_lookup",
            "legacy and current Tool Manager lookup interfaces are supported",
        )
        if "def _get_registered_tool" in semantic_router
        and 'getattr(manager, "get_tool", None)' in semantic_router
        and 'getattr(manager, "get_func", None)' in semantic_router
        else fail(
            "code.semantic_router_tool_lookup",
            "semantic router cannot resolve tools across Tool Manager versions",
        )
    )
    capability_seed = (
        ROOT / "data/plugins/astrbot_plugin_semantic_router/plugin_capabilities.json"
    )
    runtime_capability_seed = (
        ROOT
        / "data/plugin_data/astrbot_plugin_semantic_router/plugin_capabilities.json"
    )
    capability_seed_valid = False
    capability_seed_detail = "seed file not present"
    for seed in (runtime_capability_seed, capability_seed):
        if not seed.exists():
            continue
        try:
            payload = load_json(seed)
            entries = payload.get("capabilities") if isinstance(payload, dict) else None
            if isinstance(entries, list):
                capability_seed_valid = True
                capability_seed_detail = f"{len(entries)} seed declarations"
                break
            capability_seed_detail = "capabilities is not a list"
        except (OSError, json.JSONDecodeError) as exc:
            capability_seed_detail = f"invalid JSON: {exc}"
    checks.append(
        ok(
            "code.semantic_router_capability_catalog",
            f"live Tool Manager catalog with valid seed fallback ({capability_seed_detail})",
        )
        if capability_seed_valid
        and "def _refresh_capability_memory" in semantic_router
        and "quarantined invalid capability seed" in semantic_router
        else fail(
            "code.semantic_router_capability_catalog",
            f"capability seed or live catalog recovery is incomplete ({capability_seed_detail})",
        )
    )
    checks.append(
        ok(
            "code.semantic_router_job_context",
            "background job tools retain plugin context after FunctionTool initialization",
        )
        if 'self.__dict__["plugin"] = plugin' in semantic_router
        and 'self.__dict__["operation"] = operation' in semantic_router
        else fail(
            "code.semantic_router_job_context",
            "AgentJobControlTool may lose its plugin context",
        )
    )
    agent_tool_exec = (ROOT / "astrbot/core/astr_agent_tool_exec.py").read_text(
        encoding="utf-8-sig"
    )
    checks.append(
        ok(
            "code.mcp_tool_outcome_contract",
            "MCP None, empty, timeout, and error results are normalized",
        )
        if "async def _execute_mcp" in agent_tool_exec
        and 'error_code="empty_result"' in agent_tool_exec
        and 'error_code="mcp_error"' in agent_tool_exec
        else fail(
            "code.mcp_tool_outcome_contract",
            "MCP tools can still terminate silently on empty results",
        )
    )
    checks.append(
        ok(
            "code.semantic_router_preserves_browser",
            "QQTools browser_search is preserved instead of overwritten by fallback",
        )
        if 'self._get_registered_tool("browser_search") is None' in semantic_router
        and "preserving registered browser_search tool" in semantic_router
        else fail(
            "code.semantic_router_preserves_browser",
            "semantic router may overwrite the registered browser_search tool",
        )
    )
    checks.append(
        ok(
            "code.semantic_router_route_release",
            "LLM leases release on response, Agent completion, and message send",
        )
        if "@filter.after_message_sent(priority=200000)" in semantic_router
        and "release_route_after_send" in semantic_router
        and "@filter.on_llm_response(priority=200000)" in semantic_router
        and "release_route_after_llm_response" in semantic_router
        else fail(
            "code.semantic_router_route_release",
            "route leases can be stranded behind another stopped send hook",
        )
    )

    control_plane = (
        ROOT / "data/plugins/astrbot_plugin_semantic_router/control_plane.py"
    ).read_text(encoding="utf-8-sig")
    checks.append(
        ok(
            "code.semantic_router_commerce_and_music",
            "deal discovery requires search and generic music requests cannot become fake song names",
        )
        if all(
            marker in semantic_router
            for marker in ('"小黑盒"', '"值得买"', '"放几个"', '"随便放"')
        )
        and all(
            marker in control_plane
            for marker in ('"小黑盒"', '"优惠"', '"折扣"', '"史低"')
        )
        else fail(
            "code.semantic_router_commerce_and_music",
            "deal queries can skip search or generic music requests can produce invalid song names",
        )
    )
    checks.append(
        ok(
            "code.semantic_router_music_delivery_chain",
            "automatic playback exposes find_music and deliver_music in one route",
        )
        if '"find_music", "deliver_music"' in control_plane
        and '"search_music",' in control_plane
        else fail(
            "code.semantic_router_music_delivery_chain",
            "automatic playback can stop after candidate search because delivery is not allowlisted",
        )
    )
    checks.append(
        ok(
            "code.semantic_router_overload_reply",
            "FAST reserve, delayed admission, overload reply, and lease watchdog enabled",
        )
        if "llm_queue_saturated" in control_plane
        and "没让它继续挤队列" in control_plane
        and "async def acquire_route" in control_plane
        and "_expire_route_lease" in control_plane
        and "await self.control_plane.acquire_route(event)" in semantic_router
        else fail(
            "code.semantic_router_overload_reply",
            "adaptive LLM admission or abandoned-lease recovery is missing",
        )
    )
    checks.append(
        ok(
            "code.semantic_router_adaptive_mailbox",
            "mailbox admission runs after wake detection and before high-latency work",
        )
        if "priority=90000" in semantic_router
        and "async def _coalesce_mailbox" in semantic_router
        and "async def _work_budget" in semantic_router
        and 'admission_class == "CONTEXT_ONLY"' in semantic_router
        and "contextual_group_image" in semantic_router
        and 'event, text, "search", 5.0' in semantic_router
        and '"vision", 8.0' in semantic_router
        and "message_admission_audit" in control_plane
        and "capability_failure_report" in control_plane
        else fail(
            "code.semantic_router_adaptive_mailbox",
            "adaptive admission, work budgets, or metadata-only audit is missing",
        )
    )

    dailyhub_main = (ROOT / "data/plugins/astrbot_plugin_dailyhub/main.py").read_text(
        encoding="utf-8-sig"
    )
    checks.append(
        ok(
            "code.dailyhub_gold_tool",
            "get_daily_news exposes current gold prices to the Agent",
        )
        if '@filter.llm_tool(name="get_daily_news")' in dailyhub_main
        and "source(string)" in dailyhub_main
        and '"gold"' in dailyhub_main
        else fail(
            "code.dailyhub_gold_tool",
            "DailyHub gold capability is missing from its registered LLM tool",
        )
    )

    bili_main = (ROOT / "data/plugins/astrbot_plugin_bilibili/main.py").read_text(
        encoding="utf-8-sig"
    )
    bili_video_tool = (
        ROOT / "data/plugins/astrbot_plugin_bilibili/tools/bili_video_info.py"
    ).read_text(encoding="utf-8-sig")
    bili_summary_tool = (
        ROOT / "data/plugins/astrbot_plugin_bilibili/tools/bili_video_summary.py"
    ).read_text(encoding="utf-8-sig")
    control_plane_source = (
        ROOT / "data/plugins/astrbot_plugin_semantic_router/control_plane.py"
    ).read_text(encoding="utf-8-sig")
    checks.append(
        ok(
            "code.bilibili_agent_video_tool",
            "BV references use the registered read-only video capability",
        )
        if "BiliVideoInfoTool" in bili_main
        and "BiliVideoSummaryTool" in bili_main
        and "self.context.add_llm_tools(*llm_tools)" in bili_main
        and 'name: str = "bili_get_video_info"' in bili_video_tool
        and 'name: str = "bili_get_video_summary"' in bili_summary_tool
        and '"bili_get_video_info"' in control_plane_source
        and '"bili_get_video_summary"' in control_plane_source
        else fail(
            "code.bilibili_agent_video_tool",
            "Bilibili video capability is not registered or routed",
        )
    )

    spectre_main = (ROOT / "data/plugins/spectrecore/main.py").read_text(
        encoding="utf-8-sig"
    )
    checks.append(
        ok("code.spectrecore_command_skip", "command/plugin events are skipped")
        if "_is_command_event" in spectre_main and "CommandFilter" in spectre_main
        else fail(
            "code.spectrecore_command_skip", "SpectreCore command skip guard is missing"
        )
    )

    spectre_llm = (ROOT / "data/plugins/spectrecore/utils/llm_utils.py").read_text(
        encoding="utf-8-sig"
    )
    checks.append(
        ok("code.spectrecore_browser_prompt", "browser tools are preferred over Tavily")
        if "web_search_tavily" in spectre_llm
        and "browser_search" in spectre_llm
        and "browser_open" in spectre_llm
        else fail(
            "code.spectrecore_browser_prompt",
            "SpectreCore browser-search prompt guard is missing",
        )
    )

    angel_main = (ROOT / "data/plugins/astrbot_plugin_angel_heart/main.py").read_text(
        encoding="utf-8-sig"
    )
    whitelist_pos = angel_main.find("whitelist_enabled")
    private_pos = angel_main.find("检测到私聊唤醒消息")
    checks.append(
        ok(
            "code.angel_heart_whitelist_order",
            "whitelist gate runs before private wake branch",
        )
        if whitelist_pos >= 0 and private_pos >= 0 and whitelist_pos < private_pos
        else fail(
            "code.angel_heart_whitelist_order",
            "AngelHeart whitelist gate may still be bypassed",
        )
    )
    return checks


def iter_recent_logs(minutes: int) -> list[Path]:
    logs_dir = ROOT / "data/logs"
    if not logs_dir.exists():
        return []
    cutoff = datetime.now().timestamp() - minutes * 60
    return [path for path in logs_dir.glob("*.log") if path.stat().st_mtime >= cutoff]


def check_logs(minutes: int) -> list[Check]:
    paths = iter_recent_logs(minutes)
    if not paths:
        return [
            warn("logs.recent", f"no .log files updated in the last {minutes} minutes")
        ]

    fail_patterns = {
        "RESOURCE_EXHAUSTED": "Gemini/quota exhaustion appeared",
        "web_search_tavily": "built-in Tavily search was used",
        "Tavily API key is not configured": "Tavily missing-key failure appeared",
        "等待插件初始化超时": "a plugin initialization timeout appeared",
        "等待 Provider 就绪": "a plugin is waiting for a provider",
    }
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")[-200_000:] for path in paths
    )
    checks: list[Check] = [
        ok("logs.recent", f"scanned {len(paths)} recent log file(s)")
    ]
    for pattern, detail in fail_patterns.items():
        checks.append(
            fail(f"logs.bad_pattern.{pattern}", detail)
            if pattern in text
            else ok(f"logs.bad_pattern.{pattern}", "not found")
        )
    return checks


def parse_log_line_timestamp(line: str) -> float | None:
    if len(line) < 25 or not line.startswith("["):
        return None
    raw = line[1:24]
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S.%f").timestamp()
    except ValueError:
        return None


def filter_log_text_since(text: str, since_ts: float | None) -> str:
    if since_ts is None:
        return text

    kept: list[str] = []
    include_current = False
    for line in text.splitlines():
        line_ts = parse_log_line_timestamp(line)
        if line_ts is not None:
            include_current = line_ts >= since_ts
        if include_current:
            kept.append(line)
    return "\n".join(kept)


def read_recent_log_text(
    minutes: int, since_ts: float | None = None
) -> tuple[list[Path], str]:
    paths = iter_recent_logs(minutes)
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")[-200_000:] for path in paths
    )
    text = filter_log_text_since(text, since_ts)
    return paths, text


def check_startup_signals(minutes: int) -> list[Check]:
    runtime_starts = get_runtime_owner_start_timestamps()
    since_ts = min(runtime_starts) if runtime_starts else None
    paths, text = read_recent_log_text(minutes, since_ts=since_ts)
    if not paths:
        return [
            warn("startup.logs", f"no .log files updated in the last {minutes} minutes")
        ]

    scope = "current runtime" if since_ts is not None else f"last {minutes} minutes"
    checks: list[Check] = [
        ok("startup.logs", f"scanned {len(paths)} recent log file(s), scope={scope}")
    ]
    expected_signals = {
        "startup.onebot_connected": "aiocqhttp(OneBot v11) 适配器已连接",
        "startup.qqtools_browser_registered": "Browser tools registered",
        "startup.qqtools_browser_search_registered": "Browser tools registered (browser_search",
        "startup.bilibili_disabled": "Plugin astrbot_plugin_bilibili is disabled.",
        "startup.self_learning_affection": "好感度管理服务启动成功",
    }
    for name, pattern in expected_signals.items():
        checks.append(
            ok(name, "found")
            if pattern in text
            else warn(name, f"not found in recent logs: {pattern}")
        )

    disabled_plugins = set(load_preference("inactivated_plugins", []))
    livingmemory_disabled = (
        "data.plugins.astrbot_plugin_livingmemory.main" in disabled_plugins
    )
    checks.append(
        ok("startup.livingmemory_disabled", "disabled in preferences")
        if livingmemory_disabled
        else warn(
            "startup.livingmemory_disabled",
            "LivingMemory is not disabled in preferences",
        )
    )

    bad_patterns = {
        "startup.bad.plugin_timeout": "等待插件初始化超时",
        "startup.bad.provider_wait": "等待 Provider 就绪",
        "startup.bad.tavily": "Tavily API key is not configured",
        "startup.bad.gemini_429": "RESOURCE_EXHAUSTED",
    }
    for name, pattern in bad_patterns.items():
        checks.append(
            fail(name, f"found bad pattern: {pattern}")
            if pattern in text
            else ok(name, "not found")
        )
    return checks


def check_search_signals(minutes: int) -> list[Check]:
    runtime_starts = get_runtime_owner_start_timestamps()
    since_ts = min(runtime_starts) if runtime_starts else None
    paths, text = read_recent_log_text(minutes, since_ts=since_ts)
    if not paths:
        return [
            warn("search.logs", f"no .log files updated in the last {minutes} minutes")
        ]

    scope = "current runtime" if since_ts is not None else f"last {minutes} minutes"
    checks: list[Check] = [
        ok("search.logs", f"scanned {len(paths)} recent log file(s), scope={scope}")
    ]
    browser_search_usage_lines = [
        line
        for line in text.splitlines()
        if "browser_search" in line and "Browser tools registered" not in line
    ]
    checks.append(
        ok(
            "search.browser_search_used",
            "browser_search tool usage appeared in recent logs",
        )
        if browser_search_usage_lines
        else warn(
            "search.browser_search_used",
            "browser_search tool usage not found yet; send a QQ search/news query after restart",
        )
    )
    bad_patterns = {
        "search.bad.tavily_tool": "web_search_tavily",
        "search.bad.tavily_key": "Tavily API key is not configured",
        "search.bad.gemini_quota": "RESOURCE_EXHAUSTED",
    }
    for name, pattern in bad_patterns.items():
        checks.append(
            fail(name, f"found bad search-path pattern: {pattern}")
            if pattern in text
            else ok(name, "not found")
        )
    return checks


def print_checks(checks: list[Check]) -> None:
    width = max(len(check.name) for check in checks) if checks else 0
    for check in checks:
        print(f"{check.status:<4} {check.name:<{width}}  {check.detail}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-logs", action="store_true", help="Do not inspect data/logs."
    )
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="Also check local listening ports for a running AstrBot.",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Check QQTools browser search environment.",
    )
    parser.add_argument(
        "--browser-smoke",
        action="store_true",
        help="Launch a headless browser against about:blank.",
    )
    parser.add_argument(
        "--startup-signals",
        action="store_true",
        help="Inspect recent logs for post-restart health signals.",
    )
    parser.add_argument(
        "--search-signals",
        action="store_true",
        help="Inspect recent logs for browser_search usage after a QQ search test.",
    )
    parser.add_argument("--log-minutes", type=int, default=60)
    parser.add_argument("--fail-on-warn", action="store_true")
    args = parser.parse_args()

    checks: list[Check] = []
    checks.extend(check_core())
    checks.extend(check_plugin_configs())
    checks.extend(check_code_guards())
    if args.browser or args.browser_smoke:
        checks.extend(check_browser_environment(smoke=args.browser_smoke))
    if args.runtime:
        checks.extend(check_runtime_ports())
    if args.startup_signals:
        checks.extend(check_startup_signals(args.log_minutes))
    if args.search_signals:
        checks.extend(check_search_signals(args.log_minutes))
    if not args.skip_logs:
        checks.extend(check_logs(args.log_minutes))

    print_checks(checks)

    if any(check.status == "FAIL" for check in checks):
        return 1
    if args.fail_on_warn and any(check.status == "WARN" for check in checks):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
