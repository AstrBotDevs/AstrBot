from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import io
import json
import os
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
DB_PATH = ROOT / "data/data_v4.db"
REQUIRED_DISABLED_PLUGINS = {
    "data.plugins.astrbot_plugin_livingmemory.main",
    "data.plugins.astrbot_plugin_bilibili.main",
}
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
        if default_provider == "google_gemini/gemini-2.5-flash"
        else fail(
            "core.default_provider",
            f"expected google_gemini/gemini-2.5-flash, got {default_provider!r}",
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
        if persona == "catgirl"
        else fail("core.persona", f"expected catgirl, got {persona!r}")
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

    gemini_enabled = [
        p.get("id")
        for p in providers
        if str(p.get("id", "")).startswith("google_gemini/") and bool(p.get("enable"))
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
    vision_provider = next(
        (
            provider
            for provider in providers
            if provider.get("id") == "google_gemini/gemini-2.5-flash"
        ),
        {},
    )
    checks.append(
        ok("core.vision_provider", "Gemini 2.5 Flash is enabled for image input")
        if gemini_enabled == ["google_gemini/gemini-2.5-flash"]
        and gemini_sources_enabled == ["google_gemini"]
        and "image" in (vision_provider.get("modalities") or [])
        else fail(
            "core.vision_provider",
            "expected enabled Gemini 2.5 Flash with image modality; "
            f"providers={gemini_enabled}, sources={gemini_sources_enabled}, "
            f"modalities={vision_provider.get('modalities')!r}",
        )
    )
    return checks


def check_plugin_configs() -> list[Check]:
    checks: list[Check] = []

    disabled_plugins = set(load_preference("inactivated_plugins", []))
    disabled_tools = set(load_preference("inactivated_llm_tools", []))
    missing_disabled = sorted(REQUIRED_DISABLED_PLUGINS - disabled_plugins)
    checks.append(
        ok("plugins.disabled_slow", "LivingMemory and Bilibili are disabled")
        if not missing_disabled
        else fail(
            "plugins.disabled_slow",
            f"slow/no-credential plugins still active: {missing_disabled}",
        )
    )

    missing_disabled_tools = sorted(REQUIRED_DISABLED_API_SEARCH_TOOLS - disabled_tools)
    checks.append(
        ok(
            "tools.api_search_disabled",
            "API-key web search tools are disabled; QQTools browser is used",
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

    qqtools = load_json(ROOT / "data/config/astrbot_plugin_qq_tools_config.json")
    browser = qqtools.get("browser_config", {})
    permission = qqtools.get("tool_permission", {})
    allow_users = [str(user) for user in permission.get("tool_allow_users", [])]
    checks.append(
        ok("qqtools.browser", f"browser enabled for {OWNER_QQ}")
        if browser.get("browser") is True
        and OWNER_QQ in allow_users
        and "browser_*" in permission.get("admin_only_tools", [])
        else fail(
            "qqtools.browser",
            "QQTools browser must be enabled and restricted to the owner allow-list",
        )
    )

    angel = load_json(ROOT / "data/config/astrbot_plugin_angel_heart_config.json")
    angel_access = angel.get("access_control", {})
    angel_wake = angel.get("wake_interaction", {})
    checks.append(
        ok("angel_heart.passive_gate", "empty whitelist blocks passive takeover")
        if angel_access.get("whitelist_enabled") is True
        and angel_access.get("chat_ids") == []
        and angel_access.get("group_chat_enhancement") is False
        and angel_wake.get("force_reply_when_summoned") is False
        and angel_wake.get("reply_even_not_questioned") is False
        else fail("angel_heart.passive_gate", "AngelHeart is not fully gated")
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

    wakepro = load_json(ROOT / "data/config/astrbot_plugin_wakepro_config.json")
    pipeline = wakepro.get("pipeline", {})
    checks.append(
        ok("wakepro.non_blocking", "mention-only pipeline")
        if pipeline.get("steps") == ["mention(\u63d0\u53ca\u5524\u9192)"]
        and pipeline.get("blacklist_steps") == []
        else fail(
            "wakepro.non_blocking", "WakePro should not run blocking/wake/silence steps"
        )
    )

    meme = load_json(ROOT / "data/config/meme_manager_config.json")
    checks.append(
        ok("meme_manager.frequency", "low-frequency stickers")
        if meme.get("emotion_llm_provider_id") == "deepseek/deepseek-v4-pro"
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
    off_slow_flags = {
        "enable_jargon_learning": basic.get("enable_jargon_learning"),
        "enable_style_learning": basic.get("enable_style_learning"),
        "enable_realtime_learning": basic.get("enable_realtime_learning"),
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
    enabled_slow_flags = [key for key, value in off_slow_flags.items() if value is True]
    hook_timeout = float(runtime_internal.get("llm_hook_context_timeout", 999) or 999)
    checks.append(
        ok(
            "self_learning.balanced",
            "affection/mood/capture enabled; slow paths disabled",
        )
        if not disabled_expected and not enabled_slow_flags and hook_timeout <= 1.5
        else fail(
            "self_learning.balanced",
            f"disabled expected flags={disabled_expected}; enabled slow flags={enabled_slow_flags}; hook_timeout={hook_timeout}",
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
