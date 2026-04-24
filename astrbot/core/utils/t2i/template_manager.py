# astrbot/core/utils/t2i/template_manager.py

import os
import re
import shutil

from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_path


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
        self._migrate_legacy_template_variables()

    def _migrate_legacy_template_variables(self) -> None:
        """Migrate legacy template variables hidden in user templates."""
        for filename in os.listdir(self.user_template_dir):
            if not filename.endswith(".html"):
                continue

            path = os.path.join(self.user_template_dir, filename)
            content = self._read_file(path)
            migrated_content = self._migrate_legacy_template_content(content)
            if migrated_content != content:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(migrated_content)

    @staticmethod
    def _migrate_legacy_template_content(content: str) -> str:
        had_legacy_text = bool(
            re.search(
                r'decodeBase64Utf8\("\{\{\s*text_base64\s*\}\}"\)',
                content,
            ),
        )
        content = re.sub(
            r"^[ \t]*<script>\s*\{\{\s*shiki_runtime\s*\|\s*safe\s*\}\}\s*</script>[ \t]*\r?\n?",
            "",
            content,
            flags=re.MULTILINE,
        )
        content = re.sub(
            r'decodeBase64Utf8\("\{\{\s*text_base64\s*\}\}"\)',
            'document.getElementById("markdown-source").value',
            content,
        )
        content = re.sub(
            r"<script\s+id=[\"']markdown-source[\"']\s+type=[\"']text/plain[\"']>\s*\{\{\s*text\s*\|\s*safe\s*\}\}\s*</script>",
            '<textarea id="markdown-source" hidden>{{ text | safe }}</textarea>',
            content,
            flags=re.IGNORECASE,
        )
        content = content.replace(
            'document.getElementById("markdown-source").textContent',
            'document.getElementById("markdown-source").value',
        )
        content = TemplateManager._remove_decode_base64_utf8_helper(content)
        if had_legacy_text and not TemplateManager._has_markdown_source(content):
            content = TemplateManager._insert_markdown_source_element(content)
        return content

    @staticmethod
    def _has_markdown_source(content: str) -> bool:
        return bool(
            re.search(r"<[a-z][^>]*\bid=[\"']markdown-source[\"']", content),
        )

    @staticmethod
    def _insert_markdown_source_element(content: str) -> str:
        source_element = (
            '  <textarea id="markdown-source" hidden>{{ text | safe }}</textarea>\n'
        )
        marked_script = re.search(
            r"^[ \t]*<script\s+src=[\"']https://cdn\.jsdelivr\.net/npm/marked/marked\.min\.js[\"']></script>[ \t]*\r?\n?",
            content,
            flags=re.MULTILINE,
        )
        if marked_script:
            return (
                f"{content[: marked_script.start()]}"
                f"{source_element}"
                f"{content[marked_script.start() :]}"
            )

        body_close = re.search(r"</body\s*>", content, flags=re.IGNORECASE)
        if body_close:
            return (
                f"{content[: body_close.start()]}"
                f"{source_element}"
                f"{content[body_close.start() :]}"
            )

        return f"{source_element}{content}"

    @staticmethod
    def _remove_decode_base64_utf8_helper(content: str) -> str:
        lines = content.splitlines(keepends=True)
        migrated_lines: list[str] = []
        index = 0
        while index < len(lines):
            line = lines[index]
            if "function decodeBase64Utf8(base64Text)" not in line:
                migrated_lines.append(line)
                index += 1
                continue

            depth = 0
            while index < len(lines):
                depth += lines[index].count("{") - lines[index].count("}")
                index += 1
                if depth <= 0:
                    break

            if migrated_lines and not migrated_lines[-1].strip():
                migrated_lines.pop()

        return "".join(migrated_lines)

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
