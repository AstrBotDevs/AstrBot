from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from quart import Response as QuartResponse
from quart import make_response, request

from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.provider import Provider
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_path

from .route import Response, Route, RouteContext

SSE_HEARTBEAT = ": heartbeat\n\n"
TRACEBACK_FILE_RE = re.compile(r'File "([^"]+)", line (\d+)')
PLUGIN_PATH_RE = re.compile(r"data[\\/]+plugins[\\/]+([^\\/]+)")
BUILTIN_PLUGIN_PATH_RE = re.compile(r"astrbot[\\/]+builtin_stars[\\/]+([^\\/]+)")
SENSITIVE_PATTERNS = [
    (re.compile(r"\bsk-[a-zA-Z0-9_\-]{10,}\b"), "sk-****"),
    (
        re.compile(r"(Authorization\s*:\s*Bearer\s+)[^\s]+", flags=re.IGNORECASE),
        r"\1****",
    ),
    (re.compile(r"(Bearer\s+)[^\s]+", flags=re.IGNORECASE), r"\1****"),
    (
        re.compile(
            r"((?:api[-_ ]?key|password|token|secret|access[-_ ]?key)\s*[=:]\s*)[^\s,;]+",
            flags=re.IGNORECASE,
        ),
        r"\1****",
    ),
]

SYSTEM_PROMPT_DIAGNOSIS = """你是 AstrBot 的内置报错诊断助手。
你可以看到当前 AstrBot 的报错日志、相关源码片段、插件信息和版本信息。
你的任务是定位问题是谁引起的，并给出小白用户可以执行的解决方案。

要求：
1. 不要泛泛而谈。
2. 不要编造没有出现在上下文中的文件、函数或插件。
3. 如果证据不足，请明确说明“不确定”。
4. 优先判断是插件、AstrBot Core、Provider、配置、网络还是未知问题。
5. 如果是小白用户能操作的方案，请给出点击路径或明确步骤。
6. 如果需要开发者修复，请单独写 developer_solution。
7. 输出必须是 JSON，不要输出 Markdown。"""

SYSTEM_PROMPT_ASK = """你是 AstrBot 的内置报错诊断解释助手。
你正在继续解释一个已经诊断过的 AstrBot 报错。

用户可能是小白，请用简单、明确、可执行的方式回答。
不要脱离当前错误上下文。
不要编造没有证据的文件、函数、插件或命令。
如果用户问“怎么解决”，请给出分步骤操作。
如果用户问“是谁的问题”，请结合已有日志、源码和诊断结论说明。
如果用户看不懂，请用更通俗的话解释。
回答可以使用 Markdown。"""

DEFAULT_SETTINGS: dict[str, Any] = {
    "auto_analyze": False,
    "passive_record": True,
    "provider_id": "",
    "scope": "all",
    "selected_plugins": [],
    "levels": ["ERROR", "CRITICAL"],
    "include_source_context": True,
    "max_source_bytes": 200000,
    "source_context_lines": 120,
    "dedupe_window_sec": 600,
    "max_records": 500,
}

ALLOWED_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
ALLOWED_SCOPE = {"all", "core", "all_plugins", "selected_plugins"}
FORBIDDEN_SUFFIXES = {
    ".db",
    ".sqlite",
    ".log",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".zip",
    ".tar",
    ".gz",
    ".pem",
    ".key",
    ".crt",
}
FORBIDDEN_NAMES = {
    ".env",
    "node_modules",
    "dist",
    "__pycache__",
    ".venv",
    "venv",
}


def redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def parse_json_from_model_output(raw: str) -> tuple[dict[str, Any] | None, str]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload, text
    except json.JSONDecodeError:
        pass
    return None, text


class ErrorAnalysisRoute(Route):
    def __init__(self, context: RouteContext, core_lifecycle: AstrBotCoreLifecycle):
        super().__init__(context)
        self.core_lifecycle = core_lifecycle
        self.log_broker = core_lifecycle.log_broker

        self.base_dir = Path(get_astrbot_data_path()) / "error_analysis"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.settings_file = self.base_dir / "settings.json"
        self.records_file = self.base_dir / "records.jsonl"

        self.records_lock = asyncio.Lock()
        self.settings_lock = asyncio.Lock()
        self.analysis_semaphore = asyncio.Semaphore(2)
        self.event_queues: list[asyncio.Queue] = []
        self.watcher_task: asyncio.Task | None = None
        self._settings_cache: dict[str, Any] | None = None

        self.routes = {
            "/error-analysis/settings": [
                ("GET", self.get_settings),
                ("POST", self.update_settings),
            ],
            "/error-analysis/records": ("GET", self.list_records),
            "/error-analysis/record": ("GET", self.get_record),
            "/error-analysis/analyze": ("POST", self.manual_analyze),
            "/error-analysis/ignore": ("POST", self.ignore_record),
            "/error-analysis/events": ("GET", self.events),
            "/error-analysis/ask/stream": ("POST", self.ask_stream),
        }
        self.register_routes()

    async def start(self):
        if self.watcher_task is None:
            self.watcher_task = asyncio.create_task(
                self._watch_logs(),
                name="error_analysis_watcher",
            )

    async def get_settings(self):
        settings = await self._load_settings()
        return Response().ok(settings).__dict__

    async def update_settings(self):
        post_data = await request.get_json(silent=True)
        if not isinstance(post_data, dict):
            return Response().error("Missing JSON body").__dict__

        settings = await self._load_settings()
        updated = self._sanitize_settings({**settings, **post_data})
        await self._save_settings(updated)
        return Response().ok(updated).__dict__

    async def list_records(self):
        query_status = request.args.get("status")
        target_type = request.args.get("target_type")
        plugin = request.args.get("plugin")
        try:
            limit = int(request.args.get("limit", "50"))
            offset = int(request.args.get("offset", "0"))
        except ValueError:
            return Response().error("Invalid pagination params").__dict__

        limit = max(1, min(limit, 500))
        offset = max(0, offset)

        records = await self._load_records()
        records.sort(key=lambda item: float(item.get("updated_at", 0)), reverse=True)

        def _matched(item: dict[str, Any]) -> bool:
            if query_status and item.get("status") != query_status:
                return False
            if target_type and item.get("target_type") != target_type:
                return False
            if plugin and item.get("target_name") != plugin:
                return False
            return True

        filtered = [item for item in records if _matched(item)]
        items = filtered[offset : offset + limit]
        return Response().ok({"items": items, "total": len(filtered)}).__dict__

    async def get_record(self):
        record_id = request.args.get("record_id")
        if not record_id:
            return Response().error("Missing record_id").__dict__
        record = await self._get_record(record_id)
        if not record:
            return Response().error(f"Record {record_id} not found").__dict__
        return Response().ok(record).__dict__

    async def manual_analyze(self):
        post_data = await request.get_json(silent=True)
        if not isinstance(post_data, dict):
            return Response().error("Missing JSON body").__dict__

        record_id = post_data.get("record_id")
        provider_id = str(post_data.get("provider_id") or "")
        if record_id:
            ok, message = await self._analyze_record(record_id, provider_id)
            if not ok:
                return Response().error(message).__dict__
            updated = await self._get_record(record_id)
            return Response().ok(updated).__dict__

        logs = post_data.get("logs")
        if not isinstance(logs, list) or not logs:
            return Response().error("Missing logs or record_id").__dict__

        settings = await self._load_settings()
        raw = logs[0] if isinstance(logs[0], dict) else {}
        record = await self._create_record_from_log(
            raw_log=raw,
            settings=settings,
            source="manual",
            force_create=True,
        )
        if not record:
            return Response().error("Failed to create record").__dict__

        if provider_id:
            ok, message = await self._analyze_record(record["id"], provider_id)
            if not ok:
                return Response().error(message).__dict__
        updated = await self._get_record(record["id"])
        return Response().ok(updated).__dict__

    async def ignore_record(self):
        post_data = await request.get_json(silent=True)
        if not isinstance(post_data, dict):
            return Response().error("Missing JSON body").__dict__
        record_id = post_data.get("record_id")
        if not record_id:
            return Response().error("Missing record_id").__dict__

        updated = await self._update_record(
            record_id,
            {"status": "ignored", "updated_at": time.time()},
        )
        if not updated:
            return Response().error(f"Record {record_id} not found").__dict__
        await self._emit_event("record_updated", updated)
        return Response().ok(updated).__dict__

    async def events(self) -> QuartResponse:
        async def stream():
            queue = asyncio.Queue(maxsize=200)
            self.event_queues.append(queue)
            try:
                yield f"data: {json.dumps({'type': 'connected'})}\n\n"
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=20)
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    except asyncio.TimeoutError:
                        yield SSE_HEARTBEAT
            except asyncio.CancelledError:
                return
            finally:
                if queue in self.event_queues:
                    self.event_queues.remove(queue)

        response = await make_response(
            stream(),
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Transfer-Encoding": "chunked",
            },
        )
        response.timeout = None  # type: ignore[attr-defined]
        return response

    async def ask_stream(self) -> QuartResponse:
        post_data = await request.get_json(silent=True)
        if not isinstance(post_data, dict):
            return await self._error_stream_response("Missing JSON body")

        record_id = str(post_data.get("record_id") or "")
        question = str(post_data.get("question") or "").strip()
        provider_id = str(post_data.get("provider_id") or "")
        if not record_id or not question:
            return await self._error_stream_response("Missing record_id or question")

        record = await self._get_record(record_id)
        if not record:
            return await self._error_stream_response(f"Record {record_id} not found")

        if not provider_id:
            provider_id = str(record.get("provider_id") or "")
        if not provider_id:
            provider_id = str((await self._load_settings()).get("provider_id") or "")
        provider = self._get_provider(provider_id)
        if not provider:
            return await self._error_stream_response(
                f"Provider {provider_id or '(empty)'} not available"
            )

        contexts = self._build_qa_context(record, question)

        async def stream():
            answer = ""
            try:
                async for chunk in provider.text_chat_stream(
                    contexts=contexts,
                    model=provider.get_model() or None,
                ):
                    text = chunk.completion_text or ""
                    if not text:
                        continue
                    if text.startswith(answer):
                        delta = text[len(answer) :]
                    else:
                        delta = text
                    if not delta:
                        continue
                    answer += delta
                    yield (
                        "data: "
                        + json.dumps(
                            {"type": "delta", "data": delta},
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )

                updated = await self._append_qa_message(record_id, question, answer)
                if updated:
                    await self._emit_event("record_updated", updated)
                yield "data: " + json.dumps({"type": "done"}) + "\n\n"
            except Exception as exc:  # noqa: BLE001
                logger.error("[ErrorAnalysis] ask_stream failed: %s", exc)
                yield (
                    "data: "
                    + json.dumps(
                        {"type": "error", "message": str(exc)},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )

        response = await make_response(
            stream(),
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Transfer-Encoding": "chunked",
            },
        )
        response.timeout = None  # type: ignore[attr-defined]
        return response

    async def _watch_logs(self):
        queue = self.log_broker.register()
        try:
            while True:
                log_item = await queue.get()
                try:
                    await self._handle_log(log_item)
                except Exception as exc:  # noqa: BLE001
                    logger.error("[ErrorAnalysis] handle log failed: %s", exc)
        except asyncio.CancelledError:
            return
        finally:
            self.log_broker.unregister(queue)

    async def _handle_log(self, raw_log: dict[str, Any]):
        level = str(raw_log.get("level") or "").upper()
        if level not in ALLOWED_LEVELS:
            return

        settings = await self._load_settings()
        if level not in settings["levels"]:
            return
        if not settings["passive_record"] and not settings["auto_analyze"]:
            return

        record = await self._create_record_from_log(
            raw_log=raw_log,
            settings=settings,
            source="auto",
            force_create=False,
        )
        if not record:
            return

        await self._emit_event("record_created", record)
        if not settings["auto_analyze"]:
            return

        provider_id = str(settings.get("provider_id") or "")
        if not provider_id:
            updated = await self._update_record(
                record["id"],
                {
                    "status": "failed",
                    "updated_at": time.time(),
                    "error_message": "No provider selected",
                },
            )
            if updated:
                await self._emit_event("record_updated", updated)
            return

        asyncio.create_task(self._run_analysis_limited(record["id"], provider_id))

    async def _run_analysis_limited(self, record_id: str, provider_id: str):
        async with self.analysis_semaphore:
            await self._analyze_record(record_id, provider_id)

    async def _create_record_from_log(
        self,
        *,
        raw_log: dict[str, Any],
        settings: dict[str, Any],
        source: str,
        force_create: bool,
    ) -> dict[str, Any] | None:
        record_meta = self._classify_target(raw_log)
        if not self._scope_matched(settings, record_meta):
            return None

        now = time.time()
        fingerprint = self._build_fingerprint(raw_log)
        async with self.records_lock:
            records = self._load_records_unlocked()
            if not force_create and self._find_duplicate_record(
                records,
                fingerprint=fingerprint,
                dedupe_window_sec=settings["dedupe_window_sec"],
                now=now,
            ):
                return None

            record_id = self._generate_record_id(now)
            record = {
                "id": record_id,
                "status": "analyzing" if settings["auto_analyze"] else "pending",
                "source": source,
                "created_at": now,
                "updated_at": now,
                "fingerprint": fingerprint,
                "provider_id": str(settings.get("provider_id") or ""),
                "target_type": record_meta["target_type"],
                "target_name": record_meta["target_name"],
                "severity": self._level_to_severity(str(raw_log.get("level") or "")),
                "summary": "Analyzing...",
                "log_level": str(raw_log.get("level") or ""),
                "source_file": str(raw_log.get("source_file") or ""),
                "source_line": int(raw_log.get("source_line") or 0),
                "pathname": str(raw_log.get("pathname") or ""),
                "log_excerpt": redact_sensitive_text(str(raw_log.get("data") or "")),
                "message": redact_sensitive_text(str(raw_log.get("message") or "")),
                "traceback": redact_sensitive_text(
                    str(raw_log.get("exc_text") or self._extract_traceback(raw_log))
                ),
                "related_files": [],
                "plugin_info": self._build_plugin_info(record_meta["target_name"]),
                "analysis": {
                    "who_caused": "Unknown",
                    "severity": "unknown",
                    "summary": "Pending analysis",
                    "reason": "",
                    "user_solution": "",
                    "developer_solution": "",
                    "risk": "",
                    "confidence": 0.0,
                    "related_files": [],
                },
                "raw_model_output": "",
                "qa_messages": [],
                "error_message": "",
            }

            records.append(record)
            records = self._trim_records(records, int(settings["max_records"]))
            self._save_records_unlocked(records)
            return record

    async def _analyze_record(
        self,
        record_id: str,
        provider_id: str,
    ) -> tuple[bool, str]:
        provider = self._get_provider(provider_id)
        if not provider:
            return False, f"Provider {provider_id} not available"

        record = await self._get_record(record_id)
        if not record:
            return False, f"Record {record_id} not found"

        settings = await self._load_settings()
        related_files = self._build_related_files(record, settings)
        prompt = self._build_diagnosis_prompt(record, settings, related_files)

        updated = await self._update_record(
            record_id,
            {
                "status": "analyzing",
                "updated_at": time.time(),
                "provider_id": provider_id,
                "related_files": related_files,
            },
        )
        if updated:
            await self._emit_event("record_updated", updated)

        try:
            resp = await provider.text_chat(
                contexts=[
                    {"role": "system", "content": SYSTEM_PROMPT_DIAGNOSIS},
                    {"role": "user", "content": prompt},
                ],
                model=provider.get_model() or None,
            )
            raw_text = resp.completion_text or ""
            parsed, parsed_text = parse_json_from_model_output(raw_text)

            if parsed is None:
                updated = await self._update_record(
                    record_id,
                    {
                        "status": "failed",
                        "updated_at": time.time(),
                        "summary": "Model returned non-JSON output",
                        "raw_model_output": redact_sensitive_text(parsed_text),
                        "error_message": "Model output is not valid JSON",
                    },
                )
                if updated:
                    await self._emit_event("record_updated", updated)
                return False, "Model output is not valid JSON"

            severity = str(parsed.get("severity") or "").lower()
            if severity not in {"low", "medium", "high", "critical", "unknown"}:
                severity = "unknown"

            analysis = {
                "who_caused": str(parsed.get("who_caused") or "Unknown"),
                "severity": severity,
                "summary": str(parsed.get("summary") or "No summary"),
                "reason": str(parsed.get("reason") or ""),
                "user_solution": str(parsed.get("user_solution") or ""),
                "developer_solution": str(parsed.get("developer_solution") or ""),
                "risk": str(parsed.get("risk") or ""),
                "confidence": float(parsed.get("confidence") or 0.0),
                "related_files": parsed.get("related_files") or [],
            }
            updated = await self._update_record(
                record_id,
                {
                    "status": "done",
                    "updated_at": time.time(),
                    "severity": analysis["severity"],
                    "summary": analysis["summary"],
                    "analysis": analysis,
                    "raw_model_output": redact_sensitive_text(parsed_text),
                    "error_message": "",
                },
            )
            if updated:
                await self._emit_event("record_updated", updated)
            return True, "ok"
        except Exception as exc:  # noqa: BLE001
            logger.error("[ErrorAnalysis] analyze failed for %s: %s", record_id, exc)
            updated = await self._update_record(
                record_id,
                {
                    "status": "failed",
                    "updated_at": time.time(),
                    "error_message": str(exc),
                },
            )
            if updated:
                await self._emit_event("record_updated", updated)
            return False, str(exc)

    async def _load_settings(self) -> dict[str, Any]:
        async with self.settings_lock:
            payload = self._load_settings_unlocked()
            return payload.copy()

    async def _save_settings(self, payload: dict[str, Any]):
        async with self.settings_lock:
            self._save_settings_unlocked(payload)

    def _load_settings_unlocked(self) -> dict[str, Any]:
        if self._settings_cache is not None:
            return self._settings_cache.copy()
        if not self.settings_file.exists():
            sanitized = self._sanitize_settings(DEFAULT_SETTINGS.copy())
            self._save_settings_unlocked(sanitized)
            return sanitized.copy()
        try:
            payload = json.loads(self.settings_file.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("invalid settings payload")
        except Exception:  # noqa: BLE001
            payload = DEFAULT_SETTINGS.copy()
        sanitized = self._sanitize_settings(payload)
        self._save_settings_unlocked(sanitized)
        return sanitized.copy()

    def _save_settings_unlocked(self, payload: dict[str, Any]):
        sanitized = self._sanitize_settings(payload)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.settings_file.write_text(
            json.dumps(sanitized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._settings_cache = sanitized.copy()

    def _sanitize_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = DEFAULT_SETTINGS.copy()
        data.update(payload)
        data["auto_analyze"] = bool(data["auto_analyze"])
        data["passive_record"] = bool(data["passive_record"])
        data["provider_id"] = str(data["provider_id"] or "")
        scope = str(data["scope"] or "all")
        data["scope"] = scope if scope in ALLOWED_SCOPE else "all"

        selected_plugins = data.get("selected_plugins")
        if not isinstance(selected_plugins, list):
            selected_plugins = []
        data["selected_plugins"] = [str(item) for item in selected_plugins if item]

        levels = data.get("levels")
        if not isinstance(levels, list):
            levels = DEFAULT_SETTINGS["levels"]
        normalized_levels = []
        for level in levels:
            level_name = str(level).upper()
            if level_name in ALLOWED_LEVELS:
                normalized_levels.append(level_name)
        data["levels"] = normalized_levels or DEFAULT_SETTINGS["levels"]

        data["include_source_context"] = bool(data["include_source_context"])
        data["max_source_bytes"] = max(
            10000, min(int(data["max_source_bytes"]), 500000)
        )
        data["source_context_lines"] = max(
            20, min(int(data["source_context_lines"]), 300)
        )
        data["dedupe_window_sec"] = max(0, min(int(data["dedupe_window_sec"]), 3600))
        data["max_records"] = max(50, min(int(data["max_records"]), 2000))
        return data

    async def _load_records(self) -> list[dict[str, Any]]:
        async with self.records_lock:
            return self._load_records_unlocked()

    async def _save_records(self, records: list[dict[str, Any]]):
        async with self.records_lock:
            self._save_records_unlocked(records)

    def _load_records_unlocked(self) -> list[dict[str, Any]]:
        if not self.records_file.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.records_file.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
                if isinstance(payload, dict):
                    records.append(payload)
            except json.JSONDecodeError:
                continue
        return records

    def _save_records_unlocked(self, records: list[dict[str, Any]]):
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with self.records_file.open("w", encoding="utf-8") as f:
            for item in records:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    async def _get_record(self, record_id: str) -> dict[str, Any] | None:
        records = await self._load_records()
        for item in records:
            if item.get("id") == record_id:
                return item
        return None

    async def _update_record(
        self,
        record_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        async with self.records_lock:
            records = self._load_records_unlocked()
            updated: dict[str, Any] | None = None
            for index, item in enumerate(records):
                if item.get("id") != record_id:
                    continue
                item = {**item, **updates}
                records[index] = item
                updated = item
                break
            if not updated:
                return None
            max_records = int(
                (self._settings_cache or DEFAULT_SETTINGS).get(
                    "max_records",
                    DEFAULT_SETTINGS["max_records"],
                )
            )
            records = self._trim_records(records, max_records)
            self._save_records_unlocked(records)
            return updated

    async def _append_qa_message(
        self,
        record_id: str,
        question: str,
        answer: str,
    ) -> dict[str, Any] | None:
        async with self.records_lock:
            records = self._load_records_unlocked()
            updated: dict[str, Any] | None = None
            now = time.time()
            for index, item in enumerate(records):
                if item.get("id") != record_id:
                    continue
                qa_messages = item.get("qa_messages")
                if not isinstance(qa_messages, list):
                    qa_messages = []
                qa_messages.append(
                    {
                        "role": "user",
                        "content": question,
                        "timestamp": now,
                    }
                )
                qa_messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "timestamp": now,
                    }
                )
                item["qa_messages"] = qa_messages[-30:]
                item["updated_at"] = now
                records[index] = item
                updated = item
                break
            if not updated:
                return None
            self._save_records_unlocked(records)
            return updated

    async def _emit_event(self, event_type: str, record: dict[str, Any]):
        payload = {"type": event_type, "record_id": record.get("id"), "record": record}
        expired_queues: list[asyncio.Queue] = []
        for queue in self.event_queues:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                continue
            except Exception:  # noqa: BLE001
                expired_queues.append(queue)
        for queue in expired_queues:
            if queue in self.event_queues:
                self.event_queues.remove(queue)

    async def _error_stream_response(self, message: str) -> QuartResponse:
        async def stream():
            yield (
                "data: "
                + json.dumps({"type": "error", "message": message}, ensure_ascii=False)
                + "\n\n"
            )
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"

        response = await make_response(
            stream(),
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        response.timeout = None  # type: ignore[attr-defined]
        return response

    def _generate_record_id(self, ts: float) -> str:
        return f"ea_{int(ts * 1000)}_{uuid.uuid4().hex[:8]}"

    def _build_fingerprint(self, raw_log: dict[str, Any]) -> str:
        text = "|".join(
            [
                str(raw_log.get("level") or ""),
                str(raw_log.get("message") or ""),
                str(raw_log.get("pathname") or ""),
                str(raw_log.get("source_file") or ""),
                str(raw_log.get("source_line") or ""),
                str(raw_log.get("exc_text") or ""),
            ]
        )
        return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

    def _find_duplicate_record(
        self,
        records: list[dict[str, Any]],
        *,
        fingerprint: str,
        dedupe_window_sec: int,
        now: float,
    ) -> dict[str, Any] | None:
        for item in reversed(records):
            if item.get("fingerprint") != fingerprint:
                continue
            created_at = float(item.get("created_at") or 0)
            if dedupe_window_sec <= 0 or now - created_at <= dedupe_window_sec:
                return item
        return None

    def _trim_records(
        self,
        records: list[dict[str, Any]],
        max_records: int,
    ) -> list[dict[str, Any]]:
        if len(records) <= max_records:
            return records
        records.sort(key=lambda item: float(item.get("created_at", 0)))
        return records[-max_records:]

    def _extract_traceback(self, raw_log: dict[str, Any]) -> str:
        text = str(raw_log.get("data") or "")
        index = text.find("Traceback (most recent call last)")
        if index >= 0:
            return text[index:]
        return ""

    def _level_to_severity(self, level: str) -> str:
        mapping = {
            "DEBUG": "low",
            "INFO": "low",
            "WARNING": "medium",
            "ERROR": "high",
            "CRITICAL": "critical",
        }
        return mapping.get(level.upper(), "unknown")

    def _classify_target(self, raw_log: dict[str, Any]) -> dict[str, str]:
        pathname = str(raw_log.get("pathname") or "")
        source_file = str(raw_log.get("source_file") or "")
        evidence = "\n".join(
            [
                str(raw_log.get("exc_text") or ""),
                str(raw_log.get("data") or ""),
                str(raw_log.get("message") or ""),
                pathname,
                source_file,
            ]
        )
        message = evidence.lower()
        normalized_path = pathname.replace("\\", "/")

        if plugin_match := PLUGIN_PATH_RE.search(evidence):
            plugin_dir = plugin_match.group(1)
            return {"target_type": "plugin", "target_name": plugin_dir}
        if builtin_match := BUILTIN_PLUGIN_PATH_RE.search(evidence):
            plugin_dir = builtin_match.group(1)
            return {"target_type": "plugin", "target_name": plugin_dir}
        if "astrbot/core" in normalized_path:
            return {"target_type": "core", "target_name": "AstrBot Core"}
        if any(key in message for key in ["401", "403", "429", "api key", "provider"]):
            return {"target_type": "provider", "target_name": "Provider"}
        if any(
            key in message
            for key in ["timeout", "connection", "network", "dns", "ssl", "socket"]
        ):
            return {"target_type": "network", "target_name": "Network"}
        if any(key in message for key in ["config", "yaml", "json", "toml"]):
            return {"target_type": "config", "target_name": "Config"}
        return {"target_type": "unknown", "target_name": "Unknown"}

    def _scope_matched(
        self,
        settings: dict[str, Any],
        record_meta: dict[str, str],
    ) -> bool:
        scope = settings["scope"]
        target_type = record_meta["target_type"]
        target_name = record_meta["target_name"]
        selected_plugins = set(settings["selected_plugins"])
        if scope == "all":
            return True
        if scope == "core":
            return target_type == "core"
        if scope == "all_plugins":
            return target_type == "plugin"
        if scope == "selected_plugins":
            return target_type == "plugin" and target_name in selected_plugins
        return True

    def _build_plugin_info(self, plugin_name: str) -> dict[str, Any]:
        if not plugin_name or plugin_name in {"AstrBot Core", "Unknown"}:
            return {}
        for plugin in self.core_lifecycle.plugin_manager.context.get_all_stars():
            if plugin.name == plugin_name or plugin.root_dir_name == plugin_name:
                return {
                    "name": plugin.name,
                    "version": plugin.version,
                    "repo": plugin.repo or "",
                    "desc": plugin.desc,
                }
        return {"name": plugin_name}

    def _build_related_files(
        self,
        record: dict[str, Any],
        settings: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not settings.get("include_source_context", True):
            return []

        max_bytes = int(settings["max_source_bytes"])
        context_lines = int(settings["source_context_lines"])
        remaining = max_bytes

        files_to_read: list[tuple[Path, int]] = []
        if record.get("pathname"):
            files_to_read.append(
                (Path(str(record["pathname"])), int(record.get("source_line") or 1))
            )

        traceback_text = str(record.get("traceback") or "")
        for file_path, line_no in TRACEBACK_FILE_RE.findall(traceback_text):
            files_to_read.append((Path(file_path), int(line_no)))

        related_files: list[dict[str, Any]] = []
        seen = set()
        for path, line_no in files_to_read:
            key = (str(path), line_no)
            if key in seen:
                continue
            seen.add(key)
            excerpt = self._read_file_excerpt(
                path=path,
                center_line=line_no,
                context_lines=context_lines,
                max_bytes=remaining,
            )
            if not excerpt:
                continue
            related_files.append(excerpt)
            remaining -= int(excerpt.get("bytes", 0))
            if remaining <= 0 or len(related_files) >= 20:
                break
        return related_files

    def _read_file_excerpt(
        self,
        *,
        path: Path,
        center_line: int,
        context_lines: int,
        max_bytes: int,
    ) -> dict[str, Any] | None:
        if max_bytes <= 0:
            return None
        if not self._is_path_allowed(path):
            return None
        if not path.is_file():
            return None

        try:
            half = max(10, context_lines // 2)
            target_line = max(1, center_line)
            start = max(1, target_line - half)
            end = target_line + half

            selected: list[tuple[int, str]] = []
            used_bytes = 0
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for index, line in enumerate(f, start=1):
                    if index < start:
                        continue
                    if index > end:
                        break
                    encoded = line.encode("utf-8", errors="replace")
                    if used_bytes + len(encoded) > max_bytes and selected:
                        break
                    selected.append((index, line.rstrip("\n")))
                    used_bytes += len(encoded)
        except Exception:  # noqa: BLE001
            return None

        if not selected:
            return None

        line_content = "\n".join(f"{index}: {line}" for index, line in selected)
        start_line = selected[0][0]
        end_line = selected[-1][0]
        return {
            "path": str(path),
            "start_line": start_line,
            "end_line": end_line,
            "content": redact_sensitive_text(line_content),
            "bytes": used_bytes,
        }

    def _is_path_allowed(self, path: Path) -> bool:
        try:
            resolved = path.resolve(strict=False)
        except Exception:  # noqa: BLE001
            return False

        path_name = resolved.name.lower()
        if path_name in FORBIDDEN_NAMES:
            return False
        if resolved.suffix.lower() in FORBIDDEN_SUFFIXES:
            return False
        for part in resolved.parts:
            if part.lower() in FORBIDDEN_NAMES:
                return False

        project_root = Path(get_astrbot_path()).resolve(strict=False)
        plugin_root = Path(get_astrbot_data_path()).resolve(strict=False) / "plugins"
        allowed_roots = [project_root, plugin_root]
        for root in allowed_roots:
            try:
                resolved.relative_to(root.resolve(strict=False))
                return True
            except ValueError:
                continue
        return False

    def _build_diagnosis_prompt(
        self,
        record: dict[str, Any],
        settings: dict[str, Any],
        related_files: list[dict[str, Any]],
    ) -> str:
        plugin_info = record.get("plugin_info") or {}
        prompt_payload = {
            "astrbot_version": VERSION,
            "scope": settings["scope"],
            "target_type": record.get("target_type"),
            "target_name": record.get("target_name"),
            "log_excerpt": record.get("log_excerpt"),
            "traceback": record.get("traceback"),
            "plugin_info": plugin_info,
            "related_files": related_files,
        }
        body = json.dumps(prompt_payload, ensure_ascii=False, indent=2)
        return (
            "请分析以下 AstrBot 报错，并严格输出 JSON。\n"
            "字段必须包含：who_caused,severity,summary,reason,user_solution,"
            "developer_solution,risk,related_files,confidence。\n\n"
            f"{body}"
        )

    def _build_qa_context(
        self,
        record: dict[str, Any],
        question: str,
    ) -> list[dict[str, Any]]:
        analysis = record.get("analysis") or {}
        qa_messages = record.get("qa_messages")
        if not isinstance(qa_messages, list):
            qa_messages = []

        context_summary = {
            "record_id": record.get("id"),
            "target_type": record.get("target_type"),
            "target_name": record.get("target_name"),
            "severity": record.get("severity"),
            "summary": record.get("summary"),
            "analysis": analysis,
            "traceback": record.get("traceback"),
            "log_excerpt": record.get("log_excerpt"),
            "related_files": record.get("related_files"),
            "qa_messages": qa_messages[-10:],
        }
        context_text = json.dumps(context_summary, ensure_ascii=False, indent=2)
        return [
            {"role": "system", "content": SYSTEM_PROMPT_ASK},
            {
                "role": "user",
                "content": (
                    f"这是当前错误上下文：\n{context_text}\n\n用户追问：{question}"
                ),
            },
        ]

    def _get_provider(self, provider_id: str) -> Provider | None:
        if not provider_id:
            return None
        target = self.core_lifecycle.provider_manager.inst_map.get(provider_id)
        if isinstance(target, Provider):
            return target
        return None
