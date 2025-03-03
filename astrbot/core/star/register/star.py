from ..star import star_registry, StarMetadata, star_map


def register_star(name: str, author: str, desc: str, version: str, repo: str = None):
    """注册一个插件(Star)。

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

    def decorator(cls):
        star_metadata = StarMetadata(
            name=name,
            author=author,
            desc=desc,
            version=version,
            repo=repo,
            star_cls_type=cls,
            module_path=cls.__module__,
        )
        star_registry.append(star_metadata)
        star_map[cls.__module__] = star_metadata
        return cls

    return decorator
