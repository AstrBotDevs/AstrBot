"""
SubAgent Logger Module
Provides logging capabilities for dynamic subagents
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from astrbot import logger as base_logger


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LogMode(Enum):
    CONSOLE_ONLY = "console"
    FILE_ONLY = "file"
    BOTH = "both"


@dataclass
class SubAgentLogEntry:
    timestamp: str
    level: str
    session_id: str
    agent_name: str | None
    event_type: str
    message: str
    details: dict | None = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "event_type": self.event_type,
            "message": self.message,
            "details": self.details,
        }


class SubAgentLogger:
    """
    SubAgent Logger
    Provides two log levels: INFO and DEBUG
    """

    _log_level: LogLevel = LogLevel.INFO
    _log_mode: LogMode = LogMode.CONSOLE_ONLY
    _log_dir: Path = field(default_factory=lambda: Path("logs/subagents"))
    _session_logs: dict = {}
    _file_handler = None

    EVENT_CREATE = "agent_create"
    EVENT_START = "agent_start"
    EVENT_END = "agent_end"
    EVENT_ERROR = "agent_error"
    EVENT_CLEANUP = "cleanup"

    @classmethod
    def configure(
        cls, level: str = "info", mode: str = "console", log_dir: str | None = None
    ) -> None:
        cls._log_level = LogLevel.DEBUG if level == "debug" else LogLevel.INFO
        mode_map = {
            "console": LogMode.CONSOLE_ONLY,
            "file": LogMode.FILE_ONLY,
            "both": LogMode.BOTH,
        }
        cls._log_mode = mode_map.get(mode.lower(), LogMode.CONSOLE_ONLY)
        if log_dir:
            cls._log_dir = Path(log_dir)
        if cls._log_mode in [LogMode.FILE_ONLY, LogMode.BOTH]:
            cls._setup_file_handler()

    @classmethod
    def _setup_file_handler(cls) -> None:
        if cls._file_handler:
            return
        try:
            cls._log_dir.mkdir(parents=True, exist_ok=True)
            log_file = (
                cls._log_dir / f"subagent_{datetime.now().strftime('%Y%m%d')}.log"
            )

            # 使用 RotatingFileHandler 自动轮转
            cls._file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding="utf-8",
            )

            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
            cls._file_handler.setFormatter(formatter)

            fl = logging.getLogger("subagent_file")
            fl.addHandler(cls._file_handler)
            fl.setLevel(logging.DEBUG)
        except Exception as e:
            base_logger.warning(f"[SubAgentLogger] Setup error: {e}")

    @classmethod
    def should_log(cls, level: str) -> bool:
        if level == "debug":
            return cls._log_level == LogLevel.DEBUG
        return True

    @classmethod
    def log(
        cls,
        session_id: str,
        event_type: str,
        message: str,
        level: str = "info",
        agent_name: str | None = None,
        details: dict | None = None,
        error_trace: str | None = None,
    ) -> None:
        if not cls.should_log(level):
            return
        entry = SubAgentLogEntry(
            timestamp=datetime.now().isoformat(),
            level=level.upper(),
            session_id=session_id,
            agent_name=agent_name,
            event_type=event_type,
            message=message,
            details=details,
        )
        if session_id not in cls._session_logs:
            cls._session_logs[session_id] = []
        cls._session_logs[session_id].append(entry)
        prefix = f"[{agent_name}]" if agent_name else "[Main]"
        log_msg = f"{prefix} [{event_type}] {message}"
        log_func = getattr(base_logger, level, base_logger.info)
        log_func(log_msg)

    @classmethod
    def info(
        cls,
        session_id: str,
        event_type: str,
        message: str,
        agent_name: str | None = None,
        details: dict | None = None,
    ) -> None:
        cls.log(session_id, event_type, message, "info", agent_name, details)

    @classmethod
    def debug(
        cls,
        session_id: str,
        event_type: str,
        message: str,
        agent_name: str | None = None,
        details: dict | None = None,
    ) -> None:
        cls.log(session_id, event_type, message, "debug", agent_name, details)

    @classmethod
    def error(
        cls,
        session_id: str,
        event_type: str,
        message: str,
        agent_name: str | None = None,
        details: dict | None = None,
    ) -> None:
        cls.log(session_id, event_type, message, "error", agent_name, details)

    @classmethod
    def get_session_logs(cls, session_id: str) -> list[dict]:
        return [l.to_dict() for l in cls._session_logs.get(session_id, [])]

    @classmethod
    def shutdown(cls) -> None:
        if cls._file_handler:
            cls._file_handler.close()


def log_agent_create(
    session_id: str, agent_name: str, details: dict | None = None
) -> None:
    SubAgentLogger.info(
        session_id,
        SubAgentLogger.EVENT_CREATE,
        f"Agent created: {agent_name}",
        agent_name,
        details,
    )


def log_agent_start(session_id: str, agent_name: str, task: str) -> None:
    SubAgentLogger.info(
        session_id,
        SubAgentLogger.EVENT_START,
        f"Agent started: {task[:80]}...",
        agent_name,
    )


def log_agent_end(session_id: str, agent_name: str, result: str) -> None:
    SubAgentLogger.info(
        session_id,
        SubAgentLogger.EVENT_END,
        "Agent completed",
        agent_name,
        {"result": str(result)[:200]},
    )


def log_agent_error(session_id: str, agent_name: str, error: str) -> None:
    SubAgentLogger.error(
        session_id, SubAgentLogger.EVENT_ERROR, f"Agent error: {error}", agent_name
    )


def log_cleanup(session_id: str, agent_name: str) -> None:
    SubAgentLogger.info(
        session_id,
        SubAgentLogger.EVENT_CLEANUP,
        f"Agent cleaned: {agent_name}",
        agent_name,
    )
