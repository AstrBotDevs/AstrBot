import os
import uuid
from astrbot.core import AstrBotConfig, logger
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.core.config.astrbot_config import ASTRBOT_CONFIG_PATH
from astrbot.core.config.default import DEFAULT_CONFIG
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

    def _is_umo_match(self, p1: str, p2: str) -> bool:
        """判断 p2 umo 是否逻辑包含于 p1 umo"""
        p1_ls = p1.split(":")
        p2_ls = p2.split(":")

        if len(p1_ls) != 3 or len(p2_ls) != 3:
            return False  # 非法格式

        return all(p == "" or p == "*" or p == t for p, t in zip(p1_ls, p2_ls))

    def _load_conf_mapping(self, umo: str | MessageSession) -> ConfInfo:
        """获取指定 umo 的配置文件 uuid, 如果不存在则返回默认配置(返回 "default")

        Returns:
            ConfInfo: 包含配置文件的 uuid, 路径和名称等信息, 是一个 dict 类型
        """
        # uuid -> { "umop": list, "path": str, "name": str }
        abconf_data = self._get_abconf_data()
        if isinstance(umo, MessageSession):
            umo = str(umo)
        else:
            try:
                umo = str(MessageSession.from_str(umo))  # validate
            except Exception:
                return DEFAULT_CONFIG_CONF_INFO

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
        abconf_name: str | None = None,
    ) -> None:
        """保存配置文件的映射关系"""
        for part in umo_parts:
            if isinstance(part, MessageSession):
                part = str(part)
            elif not isinstance(part, str):
                raise ValueError(
                    "umo_parts must be a list of strings or MessageSession instances"
                )
        abconf_data = self.sp.get(
            "abconf_mapping", {}, scope="global", scope_id="global"
        )
        random_word = abconf_name or uuid.uuid4().hex[:8]
        abconf_data[abconf_id] = {
            "umop": umo_parts,
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
        conf_list.append(DEFAULT_CONFIG_CONF_INFO)
        abconf_mapping = self._get_abconf_data()
        for uuid_, meta in abconf_mapping.items():
            conf_list.append(ConfInfo(**meta, id=uuid_))
        return conf_list

    def create_conf(
        self,
        umo_parts: list[str] | list[MessageSession],
        config: dict = DEFAULT_CONFIG,
        name: str | None = None,
    ) -> str:
        """
        umo 由三个部分组成 [platform_id]:[message_type]:[session_id]。

        umo_parts 可以是 "::" (代表所有), 可以是 "[platform_id]::" (代表指定平台下的所有类型消息和会话)。
        """
        conf_uuid = str(uuid.uuid4())
        conf_file_name = f"abconf_{conf_uuid}.json"
        conf_path = os.path.join(get_astrbot_config_path(), conf_file_name)
        conf = AstrBotConfig(config_path=conf_path, default_config=config)
        conf.save_config()
        self._save_conf_mapping(conf_file_name, conf_uuid, umo_parts, abconf_name=name)
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

    def update_conf_info(
        self, conf_id: str, name: str | None = None, umo_parts: list[str] | None = None
    ) -> bool:
        """更新配置文件信息

        Args:
            conf_id: 配置文件的 UUID
            name: 新的配置文件名称 (可选)
            umo_parts: 新的 UMO 部分列表 (可选)

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

        # 更新 UMO 部分
        if umo_parts is not None:
            # 验证 UMO 部分格式
            for part in umo_parts:
                if isinstance(part, MessageSession):
                    part = str(part)
                elif not isinstance(part, str):
                    raise ValueError(
                        "umo_parts must be a list of strings or MessageSession instances"
                    )
            abconf_data[conf_id]["umop"] = umo_parts

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
