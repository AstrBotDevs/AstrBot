import fnmatch

from astrbot.core.utils.shared_preferences import SharedPreferences


class UmopConfigRouter:
    """UMOP 配置路由器"""

    def __init__(self, sp: SharedPreferences) -> None:
        self.umop_to_conf_id: dict[str, str] = {}
        """UMOP 到配置文件 ID 的映射"""
        self.sp = sp

    async def initialize(self) -> None:
        await self._load_routing_table()

    async def _load_routing_table(self) -> None:
        """加载路由表"""
        # 从 SharedPreferences 中加载 umop_to_conf_id 映射
        sp_data = await self.sp.get_async(
            key="umop_config_routing",
            default={},
            scope="global",
            scope_id="global",
        )
        self.umop_to_conf_id = sp_data

    @staticmethod
    def _split_umo(umo: str) -> tuple[str, str, str] | None:
        """将 UMO 拆分为 3 个部分，同时保留 session_id 中的 ':'"""
        if not isinstance(umo, str):
            return None
        parts = umo.split(":", 2)
        if len(parts) != 3:
            return None
        return parts[0], parts[1], parts[2]

    def _is_umo_match(self, p1: str, p2: str) -> bool:
        """判断 p2 umo 是否逻辑包含于 p1 umo"""
        p1_ls = self._split_umo(p1)
        p2_ls = self._split_umo(p2)

        if p1_ls is None or p2_ls is None:
            return False  # 非法格式

        return all(p == "" or fnmatch.fnmatchcase(t, p) for p, t in zip(p1_ls, p2_ls))

    def get_conf_id_for_umop(self, umo: str) -> str | None:
        """根据 UMO 获取对应的配置文件 ID

        Args:
            umo (str): UMO 字符串

        Returns:
            str | None: 配置文件 ID，如果没有找到则返回 None

        """
        for pattern, conf_id in self.umop_to_conf_id.items():
            if self._is_umo_match(pattern, umo):
                return conf_id
        return None

    async def update_routing_data(self, new_routing: dict[str, str]) -> None:
        """更新路由表

        Args:
            new_routing (dict[str, str]): 新的 UMOP 到配置文件 ID 的映射。umo 由三个部分组成 [platform_id]:[message_type]:[session_id]。
                umop 可以是 "::" (代表所有), 可以是 "[platform_id]::" (代表指定平台下的所有类型消息和会话)。

        Raises:
            ValueError: 如果 new_routing 中的 key 格式不正确

        """
        for part in new_routing:
            if self._split_umo(part) is None:
                raise ValueError(
                    "umop keys must be strings in the format [platform_id]:[message_type]:[session_id], with optional wildcards * or empty for all",
                )

        self.umop_to_conf_id = new_routing
        await self.sp.global_put("umop_config_routing", self.umop_to_conf_id)

    async def update_route(self, umo: str, conf_id: str) -> None:
        """更新一条路由

        Args:
            umo (str): UMO 字符串
            conf_id (str): 配置文件 ID

        Raises:
            ValueError: 如果 umo 格式不正确

        """
        if self._split_umo(umo) is None:
            raise ValueError(
                "umop must be a string in the format [platform_id]:[message_type]:[session_id], with optional wildcards * or empty for all",
            )

        self.umop_to_conf_id[umo] = conf_id
        await self.sp.global_put("umop_config_routing", self.umop_to_conf_id)

    async def delete_route(self, umo: str) -> None:
        """删除一条路由

        Args:
            umo (str): 需要删除的 UMO 字符串

        Raises:
            ValueError: 当 umo 格式不正确时抛出
        """

        if self._split_umo(umo) is None:
            raise ValueError(
                "umop must be a string in the format [platform_id]:[message_type]:[session_id], with optional wildcards * or empty for all",
            )

        if umo in self.umop_to_conf_id:
            del self.umop_to_conf_id[umo]
            await self.sp.global_put("umop_config_routing", self.umop_to_conf_id)
