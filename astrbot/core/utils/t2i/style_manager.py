# astrbot/core/utils/t2i/style_manager.py

import os
import shutil
import yaml
from typing import Any
from pathlib import Path
from astrbot.core.utils.t2i.pillowmd.decorates import MDDecorates
from astrbot.core.utils.t2i.pillowmd.style import MdStyle
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_path


class StyleManeger:
    COLOR_KEYS = [
        "pageLineColor",
        "unorderedListDotColor",
        "orderedListDotColor",
        "orderedListNumberColor",
        "citeUnderpainting",
        "citeSplitLineColor",
        "codeBlockUnderpainting",
        "codeBlockTitleColor",
        "formLineColor",
        "textColor",
        "textGradientEndColor",
        "linkColor",
        "expressionUnderpainting",
        "insertCodeUnderpainting",
        "idlineColor",
        "expressionTextColor",
        "insertCodeTextColor",
        "codeBlockTextColor",
        "remarkColor",
        "formTextColor",
        "formUnderpainting",
        "formTitleUnderpainting",
    ]
    STYLE_CACHE: dict[str, MdStyle] = {}
    CORE_STYLES = ["setting.yaml", "paint.png", "backgrounds"]
    DEFAULT_STYLE_NAME = "base"

    def __init__(self):
        self.builtin_style_dir = os.path.join(
            get_astrbot_path(), "astrbot", "core", "utils", "t2i", "style"
        )
        self.user_style_dir = os.path.join(
            get_astrbot_data_path(), "t2i_styles"
        )

        os.makedirs(self.user_style_dir, exist_ok=True)

        # 如果用户目录下缺少核心模板，则进行复制
        self._copy_core_styles(overwrite=False)


    def _copy_core_styles(self, overwrite: bool = False):
        """把内置整套主题（含子目录）一次性镜像到用户目录"""
        for name in self.CORE_STYLES:
            src = Path(self.builtin_style_dir) / name
            dst = Path(self.user_style_dir) / name
            if not src.exists():
                continue
            if src.is_dir():
                # 整目录递归复制
                if overwrite:
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                # 单文件
                dst.parent.mkdir(parents=True, exist_ok=True)
                if overwrite or not dst.exists():
                    shutil.copy2(src, dst)


    def _yaml_load(self, path: str):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fp:
                return yaml.safe_load(fp)
        raise FileNotFoundError(path)

    def create_style(self, data: dict):
        """
        根据给定目录加载 Markdown 风格配置并返回 MdStyle 实例。
        """
        style_path = Path(data["stylePath"]).resolve()
        # 1. 颜色字段自动转 tuple
        items: dict[str, Any] = {
            k: tuple(v) if k in self.COLOR_KEYS else v for k, v in data.items()
        }

        # 2. 取出 background & decorates，用于构建 MDDecorates
        background = items.pop("background")
        decorates_cfg = items.pop("decorates")

        # 3. 构建装饰器
        items["decorates"] = MDDecorates(
            backGroundMode=background["mode"],  # type: ignore
            backGroundData=background["data"],  # type: ignore
            topDecorates=decorates_cfg["top"],  # type: ignore
            bottomDecorates=decorates_cfg["bottom"],  # type: ignore
            backGroundsPath=style_path / "backgrounds",
        )

        # 4. 最终构造 MdStyle
        md_style = MdStyle(**items)
        self.STYLE_CACHE[style_path.name] = md_style
        return md_style




    def get_style_from_name(self, name: str | None) -> MdStyle:
        """
        根据给定目录获取 Markdown 风格配置。

        说明:
            - 优先读取缓存。
            - 若缓存中不存在，则尝试从用户目录加载。
            - 若用户目录中不存在，则尝试从内置目录加载。
        """
        name = name or self.DEFAULT_STYLE_NAME
        if name in self.STYLE_CACHE:
            return self.STYLE_CACHE[name]

        user_file = os.path.join(self.user_style_dir, name, "setting.yaml")
        if os.path.exists(user_file):
            data = self._yaml_load(user_file)
            return self.create_style(data)

        builtin_file = os.path.join(self.builtin_style_dir, name, "setting.yaml")
        if os.path.exists(builtin_file):
            data = self._yaml_load(builtin_file)
            return self.create_style(data)
        print(user_file, builtin_file)
        raise FileNotFoundError(f"样式【{name}】不存在")


    def get_style_from_dict(self, setting: dict) -> MdStyle:
        """
        加载 Markdown 风格配置， 传入色 setting 需符合渲染器要求的格式
        """
        return self.create_style(setting)
