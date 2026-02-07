import os
import uuid
from typing import TypedDict, TypeVar

from astrbot.core import AstrBotConfig, logger
from astrbot.core.config.astrbot_config import ASTRBOT_CONFIG_PATH
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.utils.astrbot_path import get_astrbot_config_path
from astrbot.core.utils.shared_preferences import SharedPreferences

_VT = TypeVar("_VT")


class ConfInfo(TypedDict):
    """Configuration information for a specific session or platform."""

    id: str  # UUID of the configuration or "default"
    name: str
    path: str  # File name to the configuration file


DEFAULT_CONFIG_CONF_INFO = ConfInfo(
    id="default",
    name="default",
    path=ASTRBOT_CONFIG_PATH,
)


class AstrBotConfigManager:
    """A class to manage the system configuration of AstrBot, aka ACM"""

    def __init__(
        self,
        default_config: AstrBotConfig,
        sp: SharedPreferences,
    ):
        self.sp = sp
        self.confs: dict[str, AstrBotConfig] = {}
        """uuid / "default" -> AstrBotConfig"""
        self.confs["default"] = default_config
        self.abconf_data = None
        self._runtime_config_mapping: dict[str, str] = {}
        self._load_all_configs()

    def _get_abconf_data(self) -> dict:
        """获取所有的 abconf 数据"""
        if self.abconf_data is None:
            self.abconf_data = self.sp.get(
                "abconf_mapping",
                {},
                scope="global",
                scope_id="global",
            )
        return self.abconf_data

    def _load_all_configs(self):
        """Load all configurations from the shared preferences."""
        abconf_data = self._get_abconf_data()
        self.abconf_data = abconf_data
        for uuid_, meta in abconf_data.items():
            filename = meta["path"]
            conf_path = os.path.join(get_astrbot_config_path(), filename)
            if os.path.exists(conf_path):
                conf = AstrBotConfig(config_path=conf_path)
                self.confs[uuid_] = conf
            else:
                logger.warning(
                    f"Config file {conf_path} for UUID {uuid_} does not exist, skipping.",
                )
                continue

    @staticmethod
    def _normalize_umo(umo: str | MessageSession) -> str | None:
        if isinstance(umo, MessageSession):
            return str(umo)
        try:
            return str(MessageSession.from_str(umo))  # validate
        except Exception:
            return None

    def set_runtime_config_id(self, umo: str | MessageSession, config_id: str) -> None:
        """保存运行时路由结果，用于按会话获取配置文件。"""
        norm = self._normalize_umo(umo)
        if not norm:
            return
        self._runtime_config_mapping[norm] = config_id

    def _get_runtime_config_id(self, umo: str | MessageSession) -> str | None:
        norm = self._normalize_umo(umo)
        if not norm:
            return None
        return self._runtime_config_mapping.get(norm)

    def _save_conf_mapping(
        self,
        abconf_path: str,
        abconf_id: str,
        abconf_name: str | None = None,
    ) -> None:
        """保存配置文件的映射关系"""
        abconf_data = self.sp.get(
            "abconf_mapping",
            {},
            scope="global",
            scope_id="global",
        )
        random_word = abconf_name or uuid.uuid4().hex[:8]
        abconf_data[abconf_id] = {
            "path": abconf_path,
            "name": random_word,
        }
        self.sp.put("abconf_mapping", abconf_data, scope="global", scope_id="global")
        self.abconf_data = abconf_data

    def get_conf(self, umo: str | MessageSession | None) -> AstrBotConfig:
        """获取指定 umo 的配置文件。如果不存在，则 fallback 到默认配置文件。"""
        if not umo:
            return self.confs["default"]
        config_id = self._get_runtime_config_id(umo)
        if not config_id:
            return self.confs["default"]

        return self.get_conf_by_id(config_id)

    def get_conf_by_id(self, config_id: str | None) -> AstrBotConfig:
        """通过配置文件 ID 获取配置；无效 ID 回退到默认配置。"""
        if not config_id:
            return self.confs["default"]

        conf = self.confs.get(config_id)
        if conf is None:
            return self.confs["default"]

        return conf

    @property
    def default_conf(self) -> AstrBotConfig:
        """获取默认配置文件"""
        return self.confs["default"]

    def get_config_info(self, umo: str | MessageSession) -> ConfInfo:
        """获取指定 umo 的配置文件元数据"""
        config_id = self._get_runtime_config_id(umo)
        if not config_id:
            return DEFAULT_CONFIG_CONF_INFO
        return self.get_config_info_by_id(config_id)

    def get_config_info_by_id(self, config_id: str) -> ConfInfo:
        """通过配置文件 ID 获取元数据，不进行路由."""
        if config_id == "default":
            return DEFAULT_CONFIG_CONF_INFO

        abconf_data = self._get_abconf_data()
        meta = abconf_data.get(config_id)
        if meta and isinstance(meta, dict) and config_id in self.confs:
            return ConfInfo(**meta, id=config_id)

        return DEFAULT_CONFIG_CONF_INFO

    def get_conf_list(self) -> list[ConfInfo]:
        """获取所有配置文件的元数据列表"""
        conf_list = []
        abconf_mapping = self._get_abconf_data()
        for uuid_, meta in abconf_mapping.items():
            if not isinstance(meta, dict):
                continue
            conf_list.append(ConfInfo(**meta, id=uuid_))
        conf_list.append(DEFAULT_CONFIG_CONF_INFO)
        return conf_list

    def create_conf(
        self,
        config: dict = DEFAULT_CONFIG,
        name: str | None = None,
    ) -> str:
        conf_uuid = str(uuid.uuid4())
        conf_file_name = f"abconf_{conf_uuid}.json"
        conf_path = os.path.join(get_astrbot_config_path(), conf_file_name)
        conf = AstrBotConfig(config_path=conf_path, default_config=config)
        conf.save_config()
        self._save_conf_mapping(conf_file_name, conf_uuid, abconf_name=name)
        self.confs[conf_uuid] = conf
        return conf_uuid

    def delete_conf(self, config_id: str) -> bool:
        """删除指定配置文件

        Args:
            config_id: 配置文件的 UUID

        Returns:
            bool: 删除是否成功

        Raises:
            ValueError: 如果试图删除默认配置文件

        """
        if config_id == "default":
            raise ValueError("不能删除默认配置文件")

        # 从映射中移除
        abconf_data = self.sp.get(
            "abconf_mapping",
            {},
            scope="global",
            scope_id="global",
        )
        if config_id not in abconf_data:
            logger.warning(f"配置文件 {config_id} 不存在于映射中")
            return False

        # 获取配置文件路径
        conf_path = os.path.join(
            get_astrbot_config_path(),
            abconf_data[config_id]["path"],
        )

        # 删除配置文件
        try:
            if os.path.exists(conf_path):
                os.remove(conf_path)
                logger.info(f"已删除配置文件: {conf_path}")
        except Exception as e:
            logger.error(f"删除配置文件 {conf_path} 失败: {e}")
            return False

        # 从内存中移除
        if config_id in self.confs:
            del self.confs[config_id]

        # 从映射中移除
        del abconf_data[config_id]
        self.sp.put("abconf_mapping", abconf_data, scope="global", scope_id="global")
        self.abconf_data = abconf_data

        logger.info(f"成功删除配置文件 {config_id}")
        return True

    def update_conf_info(self, config_id: str, name: str | None = None) -> bool:
        """更新配置文件信息

        Args:
            config_id: 配置文件的 UUID
            name: 新的配置文件名称 (可选)

        Returns:
            bool: 更新是否成功

        """
        if config_id == "default":
            raise ValueError("不能更新默认配置文件的信息")

        abconf_data = self.sp.get(
            "abconf_mapping",
            {},
            scope="global",
            scope_id="global",
        )
        if config_id not in abconf_data:
            logger.warning(f"配置文件 {config_id} 不存在于映射中")
            return False

        # 更新名称
        if name is not None:
            abconf_data[config_id]["name"] = name

        # 保存更新
        self.sp.put("abconf_mapping", abconf_data, scope="global", scope_id="global")
        self.abconf_data = abconf_data
        logger.info(f"成功更新配置文件 {config_id} 的信息")
        return True

    def g(
        self,
        umo: str | None = None,
        key: str | None = None,
        default: _VT = None,
    ) -> _VT:
        """获取配置项。umo 为 None 时使用默认配置"""
        if umo is None:
            return self.confs["default"].get(key, default)
        conf = self.get_conf(umo)
        return conf.get(key, default)
