# astrbot/core/utils/t2i/template_manager.py

import logging
import os
import re
import shutil

from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_path

logger = logging.getLogger("astrbot")

_ALLOWED_VARS = frozenset({"text", "version", "shiki_runtime"})
_DOMPURIFY_SCRIPT = (
    '<script src="https://cdn.jsdelivr.net/npm/dompurify@3.2.7/dist/purify.min.js">'
    "</script>"
)
_MARKED_SCRIPT = (
    '<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>'
)
_UNSAFE_TEXT_SAFE_FILTER = re.compile(r"\{\{\s*text\s*\|\s*safe\s*\}\}")
_DIRECT_MARKED_RENDER = re.compile(
    r"(?P<indent>[ \t]*)contentElement\.innerHTML\s*=\s*marked\.parse\(source\);"
)
_MARKDOWN_SOURCE_TEXTAREA = re.compile(
    r'<textarea\s+id="markdown-source"\s+hidden>\s*'
    r"\{\{\s*text\s*\|\s*(?:safe|e|escape)\s*\}\}"
    r"\s*</textarea>"
)
_MARKDOWN_SOURCE_VALUE_READ = re.compile(
    r'(?P<indent>[ \t]*)const\s+source\s*=\s*document\.getElementById\("markdown-source"\)\.value;'
)

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


def harden_t2i_template_content(content: str) -> str:
    """Patch legacy T2I template sinks that render user text as trusted HTML."""
    hardened = _UNSAFE_TEXT_SAFE_FILTER.sub("{{ text | e }}", content)
    hardened = _MARKDOWN_SOURCE_TEXTAREA.sub(
        '<script id="markdown-source" type="application/json">{{ text | tojson }}</script>',
        hardened,
    )

    def _replace_source_value_read(match: re.Match) -> str:
        indent = match.group("indent")
        return (
            f'{indent}const sourceNode = document.getElementById("markdown-source");\n'
            f"{indent}const source = JSON.parse(sourceNode.textContent || '\"\"');"
        )

    hardened = _MARKDOWN_SOURCE_VALUE_READ.sub(_replace_source_value_read, hardened)

    def _sanitize_marked_render(match: re.Match) -> str:
        indent = match.group("indent")
        return (
            f"{indent}const renderedHtml = marked.parse(source);\n"
            f"{indent}if (window.DOMPurify) {{\n"
            f"{indent}  contentElement.innerHTML = window.DOMPurify.sanitize(renderedHtml);\n"
            f"{indent}}} else {{\n"
            f"{indent}  contentElement.textContent = source;\n"
            f"{indent}}}"
        )

    if "window.DOMPurify.sanitize" not in hardened:
        hardened = _DIRECT_MARKED_RENDER.sub(_sanitize_marked_render, hardened)

    if (
        "window.DOMPurify.sanitize" in hardened
        and "purify.min.js" not in hardened
        and _MARKED_SCRIPT in hardened
    ):
        hardened = hardened.replace(
            _MARKED_SCRIPT,
            f"{_MARKED_SCRIPT}\n  {_DOMPURIFY_SCRIPT}",
            1,
        )

    return hardened


def validate_template_content(content: str, *, strict: bool = False) -> None:
    if _UNSAFE_TEXT_SAFE_FILTER.search(content):
        logger.warning("SSTI validation blocked template: unsafe text|safe filter")
        raise ValueError("Template renders text with the unsafe safe filter.")
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
        "astrbot_powershell.html",
        "astrbot_vitepress.html",
    ]

    def __init__(self) -> None:
        self.builtin_template_dir = os.path.join(
            get_astrbot_path(),
            "astrbot",
            "core",
            "utils",
            "t2i",
            "template",
        )
        self.user_template_dir = os.path.join(get_astrbot_data_path(), "t2i_templates")

        os.makedirs(self.user_template_dir, exist_ok=True)
        self._initialize_user_templates()

    def _copy_core_templates(self, overwrite: bool = False) -> None:
        """从内置目录复制核心模板到用户目录。"""
        for filename in self.CORE_TEMPLATES:
            src = os.path.join(self.builtin_template_dir, filename)
            dst = os.path.join(self.user_template_dir, filename)
            if os.path.exists(src) and (overwrite or not os.path.exists(dst)):
                shutil.copyfile(src, dst)

    def _initialize_user_templates(self) -> None:
        """如果用户目录下缺少核心模板，则进行复制。"""
        self._copy_core_templates(overwrite=False)
        self._harden_core_user_templates()

    def _harden_core_user_templates(self) -> None:
        """Patch copied core templates from older releases without overwriting users."""
        for filename in self.CORE_TEMPLATES:
            path = os.path.join(self.user_template_dir, filename)
            if not os.path.exists(path):
                continue

            content = self._read_file(path)
            hardened = harden_t2i_template_content(content)
            if hardened == content:
                continue

            with open(path, "w", encoding="utf-8") as f:
                f.write(hardened)

    def _get_user_template_path(self, name: str) -> str:
        """获取用户模板的完整路径，防止路径遍历漏洞。"""
        if ".." in name or "/" in name or "\\" in name:
            raise ValueError("模板名称包含非法字符。")
        return os.path.join(self.user_template_dir, f"{name}.html")

    def _read_file(self, path: str) -> str:
        """读取文件内容。"""
        with open(path, encoding="utf-8") as f:
            return f.read()

    def list_templates(self) -> list[dict]:
        """列出所有可用模板。
        该列表是内置模板和用户模板的合并视图，用户模板将覆盖同名的内置模板。
        """
        dirs_to_scan = [self.builtin_template_dir, self.user_template_dir]
        all_names = {
            os.path.splitext(f)[0]
            for d in dirs_to_scan
            for f in os.listdir(d)
            if f.endswith(".html")
        }
        return [
            {"name": name, "is_default": name == "base"} for name in sorted(all_names)
        ]

    def get_template(self, name: str) -> str:
        """获取指定模板的内容。
        优先从用户目录加载，如果不存在则回退到内置目录。
        """
        user_path = self._get_user_template_path(name)
        if os.path.exists(user_path):
            return self._read_file(user_path)

        builtin_path = os.path.join(self.builtin_template_dir, f"{name}.html")
        if os.path.exists(builtin_path):
            return self._read_file(builtin_path)

        raise FileNotFoundError("模板不存在。")

    def create_template(self, name: str, content: str) -> None:
        """在用户目录中创建一个新的模板文件。"""
        validate_template_content(content, strict=True)
        path = self._get_user_template_path(name)
        if os.path.exists(path):
            raise FileExistsError("同名模板已存在。")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def update_template(self, name: str, content: str) -> None:
        """更新一个模板。此操作始终写入用户目录。
        如果更新的是一个内置模板，此操作实际上会在用户目录中创建一个修改后的副本，
        从而实现对内置模板的“覆盖”。
        """
        validate_template_content(content, strict=True)
        path = self._get_user_template_path(name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def delete_template(self, name: str) -> None:
        """仅删除用户目录中的模板文件。
        如果删除的是一个覆盖了内置模板的用户模板，这将有效地“恢复”到内置版本。
        """
        path = self._get_user_template_path(name)
        if not os.path.exists(path):
            raise FileNotFoundError("用户模板不存在，无法删除。")
        os.remove(path)

    def reset_default_template(self) -> None:
        """将核心模板从内置目录强制重置到用户目录。"""
        self._copy_core_templates(overwrite=True)
