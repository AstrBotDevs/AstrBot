"""
Astrbot统一路径获取

项目路径：固定为源码所在路径
根目录路径：默认为当前工作目录，可通过环境变量 ASTRBOT_ROOT 指定
数据目录路径：固定为根目录下的 data 目录
配置文件路径：固定为数据目录下的 config 目录
插件目录路径：固定为数据目录下的 plugins 目录
"""

import os


def get_astrbot_path() -> str:
    """获取Astrbot项目路径"""
    return os.path.realpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../")
    )


def get_astrbot_root() -> str:
    """获取Astrbot根目录路径"""
    if path := os.environ.get("ASTRBOT_ROOT"):
        return os.path.realpath(path)
    else:
        return os.path.realpath(os.getcwd())


def get_astrbot_data_path() -> str:
    """获取Astrbot数据目录路径"""
    return os.path.realpath(os.path.join(get_astrbot_root(), "data"))


def get_astrbot_config_path() -> str:
    """获取Astrbot配置文件路径"""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "config"))


def get_astrbot_plugin_path() -> str:
    """获取Astrbot插件目录路径"""
    return os.path.realpath(os.path.join(get_astrbot_data_path(), "plugins"))
