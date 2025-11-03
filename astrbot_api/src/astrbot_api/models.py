from __future__ import annotations

from pydantic import BaseModel


class AstrbotPluginMetadata(BaseModel):
    """AstrBot 插件元数据模型."""
    name: str | None = None
    """插件名"""
    author: str | None = None
    """插件作者"""
    desc: str | None = None
    """插件简介"""
    version: str | None = None
    """插件版本"""
    repo: str | None = None
    """插件仓库地址"""

    reserved: bool = False
    """是否是 AstrBot 的保留插件"""

    activated: bool = True
    """是否被激活"""

    display_name: str | None = None
    """用于展示的插件名称"""


