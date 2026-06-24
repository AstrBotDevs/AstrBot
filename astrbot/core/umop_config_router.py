# 导入 fnmatch 模块，用于 Unix 风格的文件名模式匹配（支持 * 通配符）
import fnmatch

# 导入共享偏好设置类，用于持久化存储配置数据
from astrbot.core.utils.shared_preferences import SharedPreferences


class UmopConfigRouter:
    """
    UMOP 配置路由器。
    负责管理 UMO（统一消息对象标识符）到配置文件 ID 的路由映射。
    支持通配符匹配，实现灵活的消息路由配置。
    
    UMO 格式: [platform_id]:[message_type]:[session_id]
    通配符规则:
        - "::" 匹配所有消息
        - "[platform_id]::" 匹配指定平台的所有消息
        - 使用 fnmatch 的 * 通配符进行模式匹配
    """

    def __init__(self, sp: SharedPreferences) -> None:
        """
        初始化 UMOP 配置路由器。

        Args:
            sp: SharedPreferences 实例，用于持久化存储路由配置
        """
        # 初始化 UMOP 到配置文件 ID 的映射字典
        self.umop_to_conf_id: dict[str, str] = {}
        """UMOP 到配置文件 ID 的映射"""
        # 保存 SharedPreferences 实例引用
        self.sp = sp

    async def initialize(self) -> None:
        """
        异步初始化路由器。
        从持久化存储中加载路由表数据。
        """
        # 调用内部方法加载路由表
        await self._load_routing_table()

    async def _load_routing_table(self) -> None:
        """
        从 SharedPreferences 加载路由表。
        读取持久化存储中的 UMOP 到配置 ID 的映射数据。
        """
        # 从 SharedPreferences 中异步获取路由配置数据
        sp_data = await self.sp.get_async(
            key="umop_config_routing",  # 存储键名
            default={},                 # 默认值为空字典
            scope="global",             # 全局作用域
            scope_id="global",          # 全局作用域 ID
        )
        # 更新内存中的路由映射
        self.umop_to_conf_id = sp_data

    @staticmethod
    def _split_umo(umo: str) -> tuple[str, str, str] | None:
        """
        将 UMO 字符串拆分为三个部分。
        保留 session_id 中可能存在的 ':' 字符。

        Args:
            umo: UMO 字符串，格式为 platform_id:message_type:session_id

        Returns:
            tuple[str, str, str] | None: 成功返回三元素元组 (platform_id, message_type, session_id)，
                                         如果输入不是字符串或格式不正确则返回 None
        """
        # 检查输入是否为字符串类型
        if not isinstance(umo, str):
            return None
        # 按 ':' 分割，最多分割 2 次（保留 session_id 中的 ':'）
        parts = umo.split(":", 2)
        # 验证分割结果是否为 3 个部分
        if len(parts) != 3:
            return None
        # 返回三个部分的元组
        return parts[0], parts[1], parts[2]

    def _is_umo_match(self, p1: str, p2: str) -> bool:
        """
        判断 p2 的 UMO 是否与 p1 的模式匹配。
        p1 作为模式（可包含通配符），p2 作为待匹配的完整 UMO。

        匹配规则：
            - 空字符串表示匹配所有
            - 支持 fnmatch 的通配符 * 和 ?
            - 三个部分分别匹配，全部匹配成功才返回 True

        Args:
            p1: 模式 UMO 字符串（可能包含通配符）
            p2: 完整的 UMO 字符串

        Returns:
            bool: 如果 p2 匹配 p1 的模式则返回 True，否则返回 False
        """
        # 将模式 UMO 拆分为三部分
        p1_ls = self._split_umo(p1)
        # 将待匹配 UMO 拆分为三部分
        p2_ls = self._split_umo(p2)

        # 如果任一 UMO 格式非法，返回 False
        if p1_ls is None or p2_ls is None:
            return False  # 非法格式

        # 逐部分比较：
        # p 是模式，t 是待匹配的目标
        # p == "" 表示该部分匹配所有
        # 否则使用 fnmatch 进行通配符匹配（区分大小写）
        return all(p == "" or fnmatch.fnmatchcase(t, p) for p, t in zip(p1_ls, p2_ls))

    def get_conf_id_for_umop(self, umo: str) -> str | None:
        """
        根据 UMO 获取对应的配置文件 ID。
        遍历所有路由规则，返回第一个匹配的配置 ID。

        Args:
            umo: 完整的 UMO 字符串

        Returns:
            str | None: 匹配的配置文件 ID，如果没有找到匹配则返回 None
        """
        # 遍历所有路由映射
        for pattern, conf_id in self.umop_to_conf_id.items():
            # 检查当前 UMO 是否匹配该模式
            if self._is_umo_match(pattern, umo):
                # 返回匹配的配置 ID
                return conf_id
        # 没有匹配的路由，返回 None
        return None

    async def update_routing_data(self, new_routing: dict[str, str]) -> None:
        """
        批量更新整个路由表。
        用新的路由映射替换所有现有路由。

        Args:
            new_routing: 新的 UMOP 到配置文件 ID 的映射字典。
                        UMO 格式: [platform_id]:[message_type]:[session_id]
                        支持通配符：
                            - "::" 代表匹配所有消息
                            - "[platform_id]::" 代表匹配指定平台下的所有类型消息和会话

        Raises:
            ValueError: 如果 new_routing 中的任何 key 格式不正确
        """
        # 验证所有新路由的 UMO 格式
        for part in new_routing:
            if self._split_umo(part) is None:
                # 格式不正确，抛出异常
                raise ValueError(
                    "umop keys must be strings in the format [platform_id]:[message_type]:[session_id], with optional wildcards * or empty for all",
                )

        # 更新内存中的路由映射
        self.umop_to_conf_id = new_routing
        # 持久化保存到 SharedPreferences
        await self.sp.global_put("umop_config_routing", self.umop_to_conf_id)

    async def update_route(self, umo: str, conf_id: str) -> None:
        """
        更新或添加单条路由规则。

        Args:
            umo: UMO 模式字符串
            conf_id: 对应的配置文件 ID

        Raises:
            ValueError: 如果 umo 格式不正确
        """
        # 验证 UMO 格式
        if self._split_umo(umo) is None:
            # 格式不正确，抛出异常
            raise ValueError(
                "umop must be a string in the format [platform_id]:[message_type]:[session_id], with optional wildcards * or empty for all",
            )

        # 添加或更新路由映射
        self.umop_to_conf_id[umo] = conf_id
        # 持久化保存更新后的路由表
        await self.sp.global_put("umop_config_routing", self.umop_to_conf_id)

    async def delete_route(self, umo: str) -> None:
        """
        删除一条路由规则。

        Args:
            umo: 需要删除的 UMO 模式字符串

        Raises:
            ValueError: 当 umo 格式不正确时抛出
        """
        # 验证 UMO 格式
        if self._split_umo(umo) is None:
            # 格式不正确，抛出异常
            raise ValueError(
                "umop must be a string in the format [platform_id]:[message_type]:[session_id], with optional wildcards * or empty for all",
            )

        # 检查路由是否存在
        if umo in self.umop_to_conf_id:
            # 从映射中删除该路由
            del self.umop_to_conf_id[umo]
            # 持久化保存更新后的路由表
            await self.sp.global_put("umop_config_routing", self.umop_to_conf_id)