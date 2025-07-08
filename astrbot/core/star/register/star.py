import warnings

_warned_register_star = False


def register_star(name: str, author: str, desc: str, version: str, repo: str = None):
    """注册一个插件(Star)。

    [DEPRECATED] 该装饰器已废弃，将在未来版本中移除。
    在 v3.5.19 版本之后（不含），您不需要使用该装饰器来装饰插件类，
    AstrBot 会自动识别继承自 Star 的类并将其作为插件类加载。

    Args:
        name: 插件名称。
        author: 作者。
        desc: 插件的简述。
        version: 版本号。
        repo: 仓库地址。如果没有填写仓库地址，将无法更新这个插件。

    如果需要为插件填写帮助信息，请使用如下格式：

    ```python
    class MyPlugin(star.Star):
        \'\'\'这是帮助信息\'\'\'
        ...

    帮助信息会被自动提取。使用 `/plugin <插件名> 可以查看帮助信息。`
    """

    global _warned_register_star
    if not _warned_register_star:
        _warned_register_star = True
        warnings.warn(
            "The 'register_star' decorator is deprecated and will be removed in a future version.",
            DeprecationWarning,
            stacklevel=2,
        )

    def decorator(cls):
        return cls

    return decorator
