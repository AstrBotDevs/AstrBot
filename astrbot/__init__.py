def __getattr__(name: str):
    """延迟初始化 logger，避免 CLI 客户端导入时触发 core 全量初始化"""
    if name == "logger":
        from .core.log import LogManager

        _logger = LogManager.GetLogger(log_name="astrbot")
        globals()["logger"] = _logger
        return _logger
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
