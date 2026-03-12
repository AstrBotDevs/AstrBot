"""旧版配置对象兼容类型。"""


class AstrBotConfig(dict):
    """兼容旧版 ``AstrBotConfig``。

    旧版实现本身就是 ``dict`` 的薄封装，兼容层保持这一行为。
    """
