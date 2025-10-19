import os
import uuid
from astrbot.core import AstrBotConfig, logger
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.core.config.astrbot_config import ASTRBOT_CONFIG_PATH
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.utils.astrbot_path import get_astrbot_config_path
from typing import TypeVar, TypedDict

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
        ucr: UmopConfigRouter,
        sp: SharedPreferences,
    ):
        self.sp = sp
        self.ucr = ucr
        self.confs: dict[str, AstrBotConfig] = {}
        """uuid / "default" -> AstrBotConfig"""
        self.confs["default"] = default_config
        self.abconf_data = None
        self._load_all_configs()

    def _get_abconf_data(self) -> dict:
        """获取所有的 abconf 数据"""
        if self.abconf_data is None:
            self.abconf_data = self.sp.get(
                "abconf_mapping", {}, scope="global", scope_id="global"
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
                    f"Config file {conf_path} for UUID {uuid_} does not exist, skipping."
                )
                continue

    def _load_conf_mapping(self, umo: str | MessageSession) -> ConfInfo:
        """获取指定 umo 的配置文件 uuid, 如果不存在则返回默认配置(返回 "default")

        Returns:
            ConfInfo: 包含配置文件的 uuid, 路径和名称等信息, 是一个 dict 类型
        """
        # uuid -> { "path": str, "name": str }
        abconf_data = self._get_abconf_data()

        if isinstance(umo, MessageSession):
            umo = str(umo)
        else:
            try:
                umo = str(MessageSession.from_str(umo))  # validate
            except Exception:
                return DEFAULT_CONFIG_CONF_INFO

        conf_id = self.ucr.get_conf_id_for_umop(umo)
        if conf_id:
            meta = abconf_data.get(conf_id)
            if meta and isinstance(meta, dict):
                # the bind relation between umo and conf is defined in ucr now, so we remove "umop" here
                meta.pop("umop", None)
                return ConfInfo(**meta, id=conf_id)

        return DEFAULT_CONFIG_CONF_INFO

    def _save_conf_mapping(
        self,
        abconf_path: str,
        abconf_id: str,
        abconf_name: str | None = None,
    ) -> None:
        """保存配置文件的映射关系"""
        abconf_data = self.sp.get(
            "abconf_mapping", {}, scope="global", scope_id="global"
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
        abconf_mapping = self._get_abconf_data()
        for uuid_, meta in abconf_mapping.items():
            if not isinstance(meta, dict):
                continue
            meta.pop("umop", None)
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

    def delete_conf(self, conf_id: str) -> bool:
        """删除指定配置文件

        Args:
            conf_id: 配置文件的 UUID

        Returns:
            bool: 删除是否成功

        Raises:
            ValueError: 如果试图删除默认配置文件
        """
        if conf_id == "default":
            raise ValueError("不能删除默认配置文件")

        # 从映射中移除
        abconf_data = self.sp.get(
            "abconf_mapping", {}, scope="global", scope_id="global"
        )
        if conf_id not in abconf_data:
            logger.warning(f"配置文件 {conf_id} 不存在于映射中")
            return False

        # 获取配置文件路径
        conf_path = os.path.join(
            get_astrbot_config_path(), abconf_data[conf_id]["path"]
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
        if conf_id in self.confs:
            del self.confs[conf_id]

        # 从映射中移除
        del abconf_data[conf_id]
        self.sp.put("abconf_mapping", abconf_data, scope="global", scope_id="global")
        self.abconf_data = abconf_data

        logger.info(f"成功删除配置文件 {conf_id}")
        return True

    def update_conf_info(self, conf_id: str, name: str | None = None) -> bool:
        """更新配置文件信息

        Args:
            conf_id: 配置文件的 UUID
            name: 新的配置文件名称 (可选)

        Returns:
            bool: 更新是否成功
        """
        if conf_id == "default":
            raise ValueError("不能更新默认配置文件的信息")

        abconf_data = self.sp.get(
            "abconf_mapping", {}, scope="global", scope_id="global"
        )
        if conf_id not in abconf_data:
            logger.warning(f"配置文件 {conf_id} 不存在于映射中")
            return False

        # 更新名称
        if name is not None:
            abconf_data[conf_id]["name"] = name

        # 保存更新
        self.sp.put("abconf_mapping", abconf_data, scope="global", scope_id="global")
        self.abconf_data = abconf_data
        logger.info(f"成功更新配置文件 {conf_id} 的信息")
        return True

    def g(
        self, umo: str | None = None, key: str | None = None, default: _VT = None
    ) -> _VT:
        """获取配置项。umo 为 None 时使用默认配置"""
        if umo is None:
            return self.confs["default"].get(key, default)
        conf = self.get_conf(umo)
        return conf.get(key, default)
