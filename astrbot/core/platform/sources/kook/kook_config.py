import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class KookConfig:
    """KOOK 适配器配置类"""

    # 基础配置
    token: str
    enable: bool = False
    id: str = "kook"

    # 重连配置
    reconnect_delay: int = 1
    """重连延迟基数(秒)，指数退避"""
    max_reconnect_delay: int = 60
    """最大重连延迟(秒)"""
    max_retry_delay: int = 60
    """最大重试延迟(秒)"""

    # 心跳配置
    heartbeat_interval: int = 30
    """心跳间隔(秒)"""
    heartbeat_timeout: int = 6
    """心跳超时时间(秒)"""
    max_heartbeat_failures: int = 3
    """最大心跳失败次数"""

    # 失败处理
    max_consecutive_failures: int = 5
    """最大连续失败次数"""

    @classmethod
    def from_dict(cls, config_dict: dict) -> KookConfig:
        """从字典创建配置对象"""
        return cls(
            # 适配器id 应该是不能改的
            # id=config_dict.get("id", "kook"),
            enable=config_dict.get("enable", False),
            token=config_dict.get("kook_bot_token", ""),
            reconnect_delay=config_dict.get(
                "kook_reconnect_delay",
                KookConfig.reconnect_delay,
            ),
            max_reconnect_delay=config_dict.get(
                "kook_max_reconnect_delay",
                KookConfig.max_reconnect_delay,
            ),
            max_retry_delay=config_dict.get(
                "kook_max_retry_delay",
                KookConfig.max_retry_delay,
            ),
            heartbeat_interval=config_dict.get(
                "kook_heartbeat_interval",
                KookConfig.heartbeat_interval,
            ),
            heartbeat_timeout=config_dict.get(
                "kook_heartbeat_timeout",
                KookConfig.heartbeat_timeout,
            ),
            max_heartbeat_failures=config_dict.get(
                "kook_max_heartbeat_failures",
                KookConfig.max_heartbeat_failures,
            ),
            max_consecutive_failures=config_dict.get(
                "kook_max_consecutive_failures",
                KookConfig.max_consecutive_failures,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def pretty_jsons(self, indent=2) -> str:
        dict_config = self.to_dict()
        dict_config["token"] = "*" * len(self.token) if self.token else "MISSING"
        return json.dumps(dict_config, indent=indent, ensure_ascii=False)
