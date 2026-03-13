"""
旧版 ``astrbot.core.platform.register`` 导入路径兼容入口。
TODO: 目前仅保留符号以兼容导入，后续如果需要，可以在这里实现一个基于当前平台能力的注册系统适配器。
"""



def register_platform_adapter(*args, **kwargs):
    raise NotImplementedError(
        "astrbot.core.platform.register_platform_adapter() 尚未在 v4 兼容层实现。"
    )


__all__ = ["register_platform_adapter"]
