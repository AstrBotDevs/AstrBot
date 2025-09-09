# astrbot/core/utils/t2i/template_manager.py

import os
import shutil
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_path


class TemplateManager:
    """
    负责管理 t2i HTML 模板的 CRUD 和重置操作。
    支持用户自定义模板，并确保在更新时不会被覆盖。
    """

    def __init__(self):
        # 定义内置模板目录（只读）
        self.builtin_template_dir = os.path.join(
            get_astrbot_path(), "astrbot", "core", "utils", "t2i", "template"
        )
        # 定义用户模板目录（读写）
        self.user_template_dir = os.path.join(get_astrbot_data_path(), "t2i_templates")

        # 确保两个目录都存在
        os.makedirs(self.builtin_template_dir, exist_ok=True)
        os.makedirs(self.user_template_dir, exist_ok=True)

        # 初始化用户模板
        self._initialize_user_templates()

    def _initialize_user_templates(self):
        """
        如果用户目录下缺少核心模板，则从内置目录复制。
        """
        core_templates = ["base.html", "astrbot_powershell.html"]
        for template_filename in core_templates:
            user_path = os.path.join(self.user_template_dir, template_filename)
            if not os.path.exists(user_path):
                builtin_path = os.path.join(self.builtin_template_dir, template_filename)
                if os.path.exists(builtin_path):
                    shutil.copyfile(builtin_path, user_path)

    def _get_user_template_path(self, name: str) -> str:
        """获取用户模板的完整路径，防止路径遍历漏洞。"""
        if ".." in name or "/" in name or "\\" in name:
            raise ValueError("模板名称包含非法字符。")
        return os.path.join(self.user_template_dir, f"{name}.html")

    def list_templates(self) -> list[dict]:
        """
        列出所有可用的模板，合并内置模板和用户模板。
        用户模板会覆盖同名的内置模板。
        """
        templates = {}

        # 首先加载内置模板
        for filename in os.listdir(self.builtin_template_dir):
            if filename.endswith(".html"):
                name = os.path.splitext(filename)[0]
                templates[name] = {"name": name, "is_default": name == "base"}

        # 然后加载用户模板，实现覆盖
        for filename in os.listdir(self.user_template_dir):
            if filename.endswith(".html"):
                name = os.path.splitext(filename)[0]
                templates[name] = {"name": name, "is_default": name == "base"}
        
        return list(templates.values())

    def get_template(self, name: str) -> str:
        """
        获取指定模板的内容。
        优先从用户目录加载，如果不存在则回退到内置目录。
        """
        user_path = self._get_user_template_path(name)
        
        # 优先查找用户目录
        if os.path.exists(user_path):
            with open(user_path, "r", encoding="utf-8") as f:
                return f.read()

        # 回退到内置目录
        builtin_path = os.path.join(self.builtin_template_dir, f"{name}.html")
        if os.path.exists(builtin_path):
            with open(builtin_path, "r", encoding="utf-8") as f:
                return f.read()
        
        raise FileNotFoundError("模板不存在。")

    def create_template(self, name: str, content: str):
        """在用户目录中创建一个新的模板文件。"""
        path = self._get_user_template_path(name)
        if os.path.exists(path):
            raise FileExistsError("同名模板已存在。")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def update_template(self, name: str, content: str):
        """更新一个用户目录中的模板文件。"""
        path = self._get_user_template_path(name)
        # 即使用户模板不存在（即正在修改的是内置模板的“副本”）也直接写入用户目录
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def delete_template(self, name: str):
        """仅删除用户目录中的模板文件。"""
        if name == "base":
            raise ValueError("不能删除默认的 base 模板。")
        path = self._get_user_template_path(name)
        if not os.path.exists(path):
            raise FileNotFoundError("用户模板不存在，无法删除。")
        os.remove(path)

    def reset_default_template(self):
        """
        将 'base.html' 和 'astrbot_powershell.html' 从内置目录重置到用户目录。
        """
        core_templates = ["base.html", "astrbot_powershell.html"]
        for template_filename in core_templates:
            builtin_path = os.path.join(self.builtin_template_dir, template_filename)
            if os.path.exists(builtin_path):
                user_path = os.path.join(self.user_template_dir, template_filename)
                shutil.copyfile(builtin_path, user_path)
