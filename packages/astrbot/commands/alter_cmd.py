import astrbot.api.star as star
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.utils.command_parser import CommandParserMixin
from astrbot.core.star.star_handler import star_handlers_registry, StarHandlerMetadata
from astrbot.core.star.star import star_map
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from enum import Enum


class RstScene(Enum):
    GROUP_UNIQUE_ON = ("group_unique_on", "群聊+会话隔离开启")
    GROUP_UNIQUE_OFF = ("group_unique_off", "群聊+会话隔离关闭")
    PRIVATE = ("private", "私聊")

    @property
    def key(self) -> str:
        return self.value[0]

    @property
    def name(self) -> str:
        return self.value[1]

    @classmethod
    def from_index(cls, index: int) -> "RstScene":
        mapping = {1: cls.GROUP_UNIQUE_ON, 2: cls.GROUP_UNIQUE_OFF, 3: cls.PRIVATE}
        return mapping[index]


class AlterCmdCommands(CommandParserMixin):
    def __init__(self, context: star.Context):
        self.context = context

    async def update_reset_permission(self, scene_key: str, perm_type: str):
        """更新reset命令在特定场景下的权限设置"""
        from astrbot.api import sp

        alter_cmd_cfg = await sp.global_get("alter_cmd", {})
        plugin_cfg = alter_cmd_cfg.get("astrbot", {})
        reset_cfg = plugin_cfg.get("reset", {})
        reset_cfg[scene_key] = perm_type
        plugin_cfg["reset"] = reset_cfg
        alter_cmd_cfg["astrbot"] = plugin_cfg
        await sp.global_put("alter_cmd", alter_cmd_cfg)

    async def alter_cmd(self, event: AstrMessageEvent):
        token = self.parse_commands(event.message_str)
        if token.len < 3:
            await event.send(
                MessageChain().message(
                    "该指令用于设置指令或指令组的权限。\n"
                    "格式: /alter_cmd <cmd_name> <admin/member>\n"
                    "例1: /alter_cmd c1 admin 将 c1 设为管理员指令\n"
                    "例2: /alter_cmd g1 c1 admin 将 g1 指令组的 c1 子指令设为管理员指令\n"
                    "/alter_cmd reset config 打开 reset 权限配置"
                )
            )
            return

        cmd_name = " ".join(token.tokens[1:-1])
        cmd_type = token.get(-1)

        if cmd_name == "reset" and cmd_type == "config":
            from astrbot.api import sp

            alter_cmd_cfg = await sp.global_get("alter_cmd", {})
            plugin_ = alter_cmd_cfg.get("astrbot", {})
            reset_cfg = plugin_.get("reset", {})

            group_unique_on = reset_cfg.get("group_unique_on", "admin")
            group_unique_off = reset_cfg.get("group_unique_off", "admin")
            private = reset_cfg.get("private", "member")

            config_menu = f"""reset命令权限细粒度配置
                当前配置：
                1. 群聊+会话隔离开: {group_unique_on}
                2. 群聊+会话隔离关: {group_unique_off}
                3. 私聊: {private}
                修改指令格式：
                /alter_cmd reset scene <场景编号> <admin/member>
                例如: /alter_cmd reset scene 2 member"""
            await event.send(MessageChain().message(config_menu))
            return

        if cmd_name == "reset" and cmd_type == "scene" and token.len >= 4:
            scene_num = token.get(3)
            perm_type = token.get(4)

            if scene_num is None or perm_type is None:
                await event.send(MessageChain().message("场景编号和权限类型不能为空"))
                return

            if not scene_num.isdigit() or int(scene_num) < 1 or int(scene_num) > 3:
                await event.send(
                    MessageChain().message("场景编号必须是 1-3 之间的数字")
                )
                return

            if perm_type not in ["admin", "member"]:
                await event.send(
                    MessageChain().message("权限类型错误，只能是 admin 或 member")
                )
                return

            scene_num = int(scene_num)
            scene = RstScene.from_index(scene_num)
            scene_key = scene.key

            await self.update_reset_permission(scene_key, perm_type)

            await event.send(
                MessageChain().message(
                    f"已将 reset 命令在{scene.name}场景下的权限设为{perm_type}"
                )
            )
            return

        if cmd_type not in ["admin", "member"]:
            await event.send(
                MessageChain().message("指令类型错误，可选类型有 admin, member")
            )
            return

        # 查找指令
        found_command = None
        cmd_group = False
        for handler in star_handlers_registry:
            assert isinstance(handler, StarHandlerMetadata)
            for filter_ in handler.event_filters:
                if isinstance(filter_, CommandFilter):
                    if filter_.equals(cmd_name):
                        found_command = handler
                        break
                elif isinstance(filter_, CommandGroupFilter):
                    if filter_.equals(cmd_name):
                        found_command = handler
                        cmd_group = True
                        break

        if not found_command:
            await event.send(MessageChain().message("未找到该指令"))
            return

        found_plugin = star_map[found_command.handler_module_path]

        from astrbot.api import sp

        alter_cmd_cfg = await sp.global_get("alter_cmd", {})
        plugin_ = alter_cmd_cfg.get(found_plugin.name, {})
        cfg = plugin_.get(found_command.handler_name, {})
        cfg["permission"] = cmd_type
        plugin_[found_command.handler_name] = cfg
        alter_cmd_cfg[found_plugin.name] = plugin_

        await sp.global_put("alter_cmd", alter_cmd_cfg)

        # 注入权限过滤器
        found_permission_filter = False
        for filter_ in found_command.event_filters:
            if isinstance(filter_, PermissionTypeFilter):
                if cmd_type == "admin":
                    import astrbot.api.event.filter as filter

                    filter_.permission_type = filter.PermissionType.ADMIN
                else:
                    import astrbot.api.event.filter as filter

                    filter_.permission_type = filter.PermissionType.MEMBER
                found_permission_filter = True
                break
        if not found_permission_filter:
            import astrbot.api.event.filter as filter

            found_command.event_filters.insert(
                0,
                PermissionTypeFilter(
                    filter.PermissionType.ADMIN
                    if cmd_type == "admin"
                    else filter.PermissionType.MEMBER
                ),
            )
        cmd_group_str = "指令组" if cmd_group else "指令"
        await event.send(
            MessageChain().message(
                f"已将「{cmd_name}」{cmd_group_str} 的权限级别调整为 {cmd_type}。"
            )
        )
