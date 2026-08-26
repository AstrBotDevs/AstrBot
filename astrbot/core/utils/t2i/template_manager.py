# astrbot/core/utils/t2i/template_manager.py

import hashlib
import logging
import re
from pathlib import Path

from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_path

logger = logging.getLogger("astrbot")

_ALLOWED_VARS = frozenset({"rendered_html", "shiki_runtime", "text", "version"})

# Unmodified copies of previous built-in templates. Matching hashes are safe
# to drop so the current Playwright-rendered built-in template is used.
_LEGACY_UNMODIFIED_CORE_TEMPLATE_HASHES = {
    "base.html": frozenset(
        {
            "260af3eda8558d36ee307aa84698cf3708fdf1cc9e2a55f193b15615b98555b3",
        }
    )
}

_SSTI_BLACKLIST: list[tuple[str, re.Pattern]] = [
    (
        "dunder_chain",
        re.compile(
            r"__\s*(class|globals|init|mro|base|bases|subclasses|reduce|getitem|builtins|import|self|func|code|reduce_ex)__"
        ),
    ),
    (
        "dangerous_builtins",
        re.compile(
            r"\b(import\s+(?!url)|os\.\w+|subprocess\.|\.popen\(|eval\(|exec\()"
        ),
    ),
    ("flask_context", re.compile(r"\{\{.*?\b(config|request|session|g)\b.*?\}\}")),
]

_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*(\|[^}]*)?\}\}")


def validate_template_content(content: str, *, strict: bool = False) -> None:
    for label, pattern in _SSTI_BLACKLIST:
        if pattern.search(content):
            logger.warning(f"SSTI validation blocked template: matched rule [{label}]")
            raise ValueError(f"Template contains forbidden pattern ({label}).")
    if strict:
        for m in _VAR_RE.finditer(content):
            var = m.group(1)
            if var not in _ALLOWED_VARS:
                logger.warning(
                    f"SSTI validation blocked template: unauthorized variable '{var}'"
                )
                raise ValueError(
                    f"Unauthorized Jinja2 variable '{var}'; "
                    f"allowed: {', '.join(sorted(_ALLOWED_VARS))}."
                )


class TemplateManager:
    """负责管理 t2i HTML 模板的 CRUD 和重置操作。
    采用“用户覆盖内置”策略：用户模板存储在 data 目录中，并优先于内置模板加载。
    所有创建、更新、删除操作仅影响用户目录，以确保更新框架时用户数据安全。
    """

    CORE_TEMPLATES = [
        "base.html",
        "astrbot_help.html",
        "astrbot_powershell.html",
        "astrbot_vitepress.html",
    ]

    def __init__(self) -> None:
        self.builtin_template_dir = (
            Path(get_astrbot_path()) / "astrbot" / "core" / "utils" / "t2i" / "template"
        )
        self.user_template_dir = Path(get_astrbot_data_path()) / "t2i_templates"

        self.user_template_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_core_template_overrides()

    def _get_user_template_path(self, name: str) -> Path:
        """获取用户模板的完整路径，防止路径遍历漏洞。"""
        if ".." in name or "/" in name or "\\" in name:
            raise ValueError("模板名称包含非法字符。")
        return self.user_template_dir / f"{name}.html"

    @staticmethod
    def _read_file(path: Path) -> str:
        """读取文件内容。"""
        return path.read_text(encoding="utf-8")

    def _migrate_core_template_overrides(self) -> None:
        """Remove unmodified core copies and back up incompatible legacy overrides."""
        for filename in self.CORE_TEMPLATES:
            builtin_path = self.builtin_template_dir / filename
            user_path = self.user_template_dir / filename
            if not builtin_path.exists() or not user_path.exists():
                continue

            try:
                user_content = self._read_file(user_path)
                normalized = user_content.replace("\r\n", "\n")
                content_hash = hashlib.sha256(normalized.encode()).hexdigest()
                if user_content == self._read_file(
                    builtin_path
                ) or content_hash in _LEGACY_UNMODIFIED_CORE_TEMPLATE_HASHES.get(
                    filename, ()
                ):
                    user_path.unlink()
                elif (
                    "marked.min.js" in user_content
                    and "markdown-source" in user_content
                ):
                    backup_path = user_path.with_suffix(".html.legacy")
                    backup_path.unlink(missing_ok=True)
                    user_path.replace(backup_path)
                    logger.warning(
                        "Moved legacy T2I template override to %s; the current built-in template will be used.",
                        backup_path,
                    )
            except OSError as exc:
                logger.warning("Failed to migrate T2I template %s: %s", user_path, exc)

    def list_templates(self) -> list[dict]:
        """列出所有可用模板。
        该列表是内置模板和用户模板的合并视图，用户模板将覆盖同名的内置模板。
        """
        dirs_to_scan = [self.builtin_template_dir, self.user_template_dir]
        all_names = {
            path.stem
            for d in dirs_to_scan
            for path in d.iterdir()
            if path.is_file() and path.suffix == ".html"
        }
        return [
            {"name": name, "is_default": name == "base"} for name in sorted(all_names)
        ]

    def get_template(self, name: str) -> str:
        """获取指定模板的内容。
        优先从用户目录加载，如果不存在则回退到内置目录。
        """
        user_path = self._get_user_template_path(name)
        if user_path.exists():
            return self._read_file(user_path)

        builtin_path = self.builtin_template_dir / f"{name}.html"
        if builtin_path.exists():
            return self._read_file(builtin_path)

        raise FileNotFoundError("模板不存在。")

    def create_template(self, name: str, content: str) -> None:
        """在用户目录中创建一个新的模板文件。"""
        validate_template_content(content, strict=True)
        path = self._get_user_template_path(name)
        builtin_path = self.builtin_template_dir / f"{name}.html"
        if path.exists() or builtin_path.exists():
            raise FileExistsError("同名模板已存在。")
        path.write_text(content, encoding="utf-8")

    def update_template(self, name: str, content: str) -> None:
        """更新一个模板。此操作始终写入用户目录。
        如果更新的是一个内置模板，此操作实际上会在用户目录中创建一个修改后的副本，
        从而实现对内置模板的“覆盖”。
        """
        validate_template_content(content, strict=True)
        path = self._get_user_template_path(name)
        path.write_text(content, encoding="utf-8")

    def delete_template(self, name: str) -> None:
        """仅删除用户目录中的模板文件。
        如果删除的是一个覆盖了内置模板的用户模板，这将有效地“恢复”到内置版本。
        """
        path = self._get_user_template_path(name)
        if not path.exists():
            raise FileNotFoundError("用户模板不存在，无法删除。")
        path.unlink()

    def reset_default_template(self) -> None:
        """Remove core template overrides and restore built-in versions."""
        for filename in self.CORE_TEMPLATES:
            (self.user_template_dir / filename).unlink(missing_ok=True)
