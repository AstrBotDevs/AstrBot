# astrbot/core/utils/t2i/template_manager.py

import os
import shutil
from astrbot.core.utils.astrbot_path import get_astrbot_path


class TemplateManager:
    """
    负责管理 t2i HTML 模板的 CRUD 和重置操作。
    """

    def __init__(self):
        # 修正路径拼接，加入缺失的 'astrbot' 目录
        self.template_dir = os.path.join(
            get_astrbot_path(), "astrbot", "core", "utils", "t2i", "template"
        )
        self.backup_template_path = os.path.join(
            self.template_dir, "default_template.html.bak"
        )
        # 确保模板目录存在
        os.makedirs(self.template_dir, exist_ok=True)

        # 检查模板目录中是否有 .html 文件
        html_files = [f for f in os.listdir(self.template_dir) if f.endswith(".html")]
        if not html_files and os.path.exists(self.backup_template_path):
            self.reset_default_template()

    def _get_template_path(self, name: str) -> str:
        """获取模板的完整路径，防止路径遍历漏洞。"""
        if ".." in name or "/" in name or "\\" in name:
            raise ValueError("模板名称包含非法字符。")
        return os.path.join(self.template_dir, f"{name}.html")

    def list_templates(self) -> list[dict]:
        """列出所有可用的模板。"""
        templates = []
        for filename in os.listdir(self.template_dir):
            if filename.endswith(".html"):
                templates.append(
                    {
                        "name": os.path.splitext(filename)[0],
                        "is_default": filename == "base.html",
                    }
                )
        return templates

    def get_template(self, name: str) -> str:
        """获取指定模板的内容。"""
        path = self._get_template_path(name)
        if not os.path.exists(path):
            raise FileNotFoundError("模板不存在。")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def create_template(self, name: str, content: str):
        """创建一个新的模板文件。"""
        path = self._get_template_path(name)
        if os.path.exists(path):
            raise FileExistsError("同名模板已存在。")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def update_template(self, name: str, content: str):
        """更新一个已存在的模板文件。"""
        path = self._get_template_path(name)
        if not os.path.exists(path):
            raise FileNotFoundError("模板不存在。")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def delete_template(self, name: str):
        """删除一个模板文件。"""
        if name == "base":
            raise ValueError("不能删除默认的 base 模板。")
        path = self._get_template_path(name)
        if not os.path.exists(path):
            raise FileNotFoundError("模板不存在。")
        os.remove(path)

    def backup_default_template_if_not_exist(self):
        """如果备份不存在，则创建默认模板的备份。"""
        default_path = os.path.join(self.template_dir, "base.html")
        if not os.path.exists(self.backup_template_path) and os.path.exists(
            default_path
        ):
            shutil.copyfile(default_path, self.backup_template_path)

    def reset_default_template(self):
        """重置默认模板。"""
        if not os.path.exists(self.backup_template_path):
            raise FileNotFoundError("默认模板的备份文件不存在，无法重置。")

        default_path = os.path.join(self.template_dir, "base.html")
        shutil.copyfile(self.backup_template_path, default_path)
