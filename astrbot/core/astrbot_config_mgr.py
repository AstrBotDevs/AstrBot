import os
import uuid
from astrbot.core import AstrBotConfig, logger
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.core.config.astrbot_config import ASTRBOT_CONFIG_PATH
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.utils.astrbot_path import get_astrbot_config_path
from typing import TypeVar, TypedDict

_VT = TypeVar("_VT")


class ConfInfo(TypedDict):
    """Configuration information for a specific session or platform."""

    id: str  # UUID of the configuration or "default"
    umop: list[str]  # Unified Message Origin Pattern
    name: str
    path: str  # File name to the configuration file


DEFAULT_CONFIG_CONF_INFO = ConfInfo(
    id="default",
    umop=["::"],
    name="default",
    path=ASTRBOT_CONFIG_PATH,
)


class AstrBotConfigManager:
    """A class to manage the system configuration of AstrBot, aka ACM"""

    def __init__(self, default_config: AstrBotConfig, sp: SharedPreferences):
        self.sp = sp
        self.confs: dict[str, AstrBotConfig] = {}
        """uuid / "default" -> AstrBotConfig"""
        self.confs["default"] = default_config
        self._load_all_configs()

    def _load_all_configs(self):
        """Load all configurations from the shared preferences."""
        abconf_data = self.sp.get("abconf_mapping", {})
        for uuid_, meta in abconf_data.items():
            filename = meta["path"]
            conf_path = os.path.join(get_astrbot_config_path(), filename)
            if os.path.exists(conf_path):
                conf = AstrBotConfig(config_path=conf_path)
                self.confs[uuid_] = conf
            else:
                logger.warning(
                    f"Config file {conf_path} for UUID {uuid_} does not exist, skipping."
                )
                continue

    def _is_umo_match(p1: str, p2: str) -> bool:
        """判断 p2 umo 是否逻辑包含于 p1 umo"""
        p1 = p1.split(":")
        p2 = p2.split(":")

        if len(p1) != 3 or len(p2) != 3:
            return False  # 非法格式

        return all(p == "" or p == t for p, t in zip(p1, p2))

    def _load_conf_mapping(self, umo: str | MessageSession) -> ConfInfo:
        """获取指定 umo 的配置文件 uuid, 如果不存在则返回默认配置(返回 "default")

        Returns:
            ConfInfo: 包含配置文件的 uuid, 路径和名称等信息, 是一个 dict 类型
        """
        # uuid -> { "umop": list, "path": str, "name": str }
        abconf_data = self.sp.get("abconf_mapping", {})
        if isinstance(umo, MessageSession):
            umo = str(umo)
        else:
            umo = str(MessageSession.from_str(umo))  # validate

        for uuid_, meta in abconf_data.items():
            for pattern in meta["umop"]:
                if self._is_umo_match(pattern, umo):
                    return ConfInfo(**meta, id=uuid_)

        return DEFAULT_CONFIG_CONF_INFO

    def _save_conf_mapping(
        self,
        abconf_path: str,
        abconf_id: str,
        umo_parts: list[str] | list[MessageSession],
        abconf_name: str = None,
    ) -> None:
        """保存配置文件的映射关系"""
        for part in umo_parts:
            if isinstance(part, MessageSession):
                part = str(part)
            elif not isinstance(part, str):
                raise ValueError(
                    "umo_parts must be a list of strings or MessageSession instances"
                )
        abconf_data = self.sp.get("abconf_mapping", {})
        random_word = abconf_name or uuid.uuid4().hex[:8]
        abconf_data[abconf_id] = {
            "umop": umo_parts,
            "path": abconf_path,
            "name": random_word,
        }
        self.sp.put("abconf_mapping", abconf_data)

    def get_conf(self, umo: str | MessageSession) -> AstrBotConfig:
        """获取指定 umo 的配置文件。如果不存在，则 fallback 到默认配置文件。"""
        if isinstance(umo, MessageSession):
            umo = f"{umo.platform_id}:{umo.message_type}:{umo.session_id}"

        uuid_ = self._load_conf_mapping(umo)["id"]

        conf = self.confs.get(uuid_)
        if not conf:
            conf = self.confs["default"]  # default MUST exists

        return conf

    @property
    def default_conf(self) -> AstrBotConfig:
        """获取默认配置文件"""
        return self.confs["default"]

    def get_conf_info(self, umo: str | MessageSession) -> ConfInfo:
        """获取指定 umo 的配置文件元数据"""
        if isinstance(umo, MessageSession):
            umo = f"{umo.platform_id}:{umo.message_type}:{umo.session_id}"

        return self._load_conf_mapping(umo)

    def get_conf_list(self) -> list[ConfInfo]:
        """获取所有配置文件的元数据列表"""
        conf_list = []
        conf_list.append(DEFAULT_CONFIG_CONF_INFO)
        for uuid_, meta in self.sp.get("abconf_mapping", {}).items():
            conf_list.append(ConfInfo(**meta, id=uuid_))
        return conf_list

    def create_conf(
        self,
        umo_parts: list[str] | list[MessageSession],
        config: dict,
        name: str = None,
    ) -> AstrBotConfig:
        """
        umo 由三个部分组成 [platform_id]:[message_type]:[session_id]。

        umo_parts 可以是 "::" (代表所有), 可以是 "[platform_id]::" (代表指定平台下的所有类型消息和会话)。
        """
        conf_uuid = str(uuid.uuid4())
        conf_file_name = f"{conf_uuid}.json"
        conf = AstrBotConfig(config_path=conf_file_name, default_config=config)
        conf.save_config()
        self._save_conf_mapping(conf_file_name, conf_uuid, umo_parts, abconf_name=name)
        self.confs[conf_uuid] = conf
        return conf

    def g(self, umo: str = None, key: str = None, default: _VT = None) -> _VT:
        """获取配置项。umo 为 None 时使用默认配置"""
        if umo is None:
            return self.confs["default"].get(key, default)
        conf = self.get_conf(umo)
        return conf.get(key, default)
