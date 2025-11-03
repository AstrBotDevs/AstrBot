"""Astrbot统一路径获取

根目录路径：默认为当前工作目录，可通过环境变量 ASTRBOT_ROOT 指定

"""

import os
import warnings

from astrbot_api.abc import IAstrbotPaths

from astrbot_sdk import sync_base_container

AstrbotPaths = sync_base_container.get(type[IAstrbotPaths])

def get_astrbot_path() -> str:
    """获取Astrbot项目路径 -- 请勿使用本函数!!! -- 仅供兼容旧代码使用"""
    warnings.warn(
        "get_astrbot_path is deprecated. Use AstrbotPaths class instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return os.path.realpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../"),
    )


def get_astrbot_root() -> str:
    """获取Astrbot根目录路径 --> get_astrbot_data_path"""
    warnings.warn(
        "不要再使用本函数!等效于: AstrbotPaths.astrbot_root",
        DeprecationWarning,
        stacklevel=2,
    )
    return str(AstrbotPaths.astrbot_root)


def get_astrbot_data_path() -> str:
    """获取Astrbot数据目录路径
    特别注意!
    这里的data目录指的就是.astrbot根目录!
    两者是等价的!
    不要和AstrbotPaths.data混淆!
    """
    warnings.warn(
        "等效于: AstrbotPaths.astrbot_root",
        DeprecationWarning,
        stacklevel=2,
    )
    return str(AstrbotPaths.astrbot_root)


def get_astrbot_config_path() -> str:
    """获取Astrbot配置文件路径"""
    warnings.warn(
        "get_astrbot_config_path is deprecated. Use AstrbotPaths class instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return str(AstrbotPaths.astrbot_root / "config")


def get_astrbot_plugin_path() -> str:
    """获取Astrbot插件目录路径"""
    warnings.warn(
        "get_astrbot_plugin_path is deprecated. Use AstrbotPaths class instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return str(AstrbotPaths.astrbot_root / "plugins")
