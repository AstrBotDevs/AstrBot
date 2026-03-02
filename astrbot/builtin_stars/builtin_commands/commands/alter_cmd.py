from astrbot.core.lang import t
from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import StarHandlerMetadata, star_handlers_registry
from astrbot.core.utils.command_parser import CommandParserMixin

from .utils.rst_scene import RstScene


class AlterCmdCommands(CommandParserMixin):
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def update_reset_permission(self, scene_key: str, perm_type: str) -> None:
        """更新reset命令在特定场景下的权限设置"""
        from astrbot.api import sp

        alter_cmd_cfg = await sp.global_get("alter_cmd", {})
        plugin_cfg = alter_cmd_cfg.get("astrbot", {})
        reset_cfg = plugin_cfg.get("reset", {})
        reset_cfg[scene_key] = perm_type
        plugin_cfg["reset"] = reset_cfg
        alter_cmd_cfg["astrbot"] = plugin_cfg
        await sp.global_put("alter_cmd", alter_cmd_cfg)

    async def alter_cmd(self, event: AstrMessageEvent) -> None:
        token = self.parse_commands(event.message_str)
        if token.len < 3:
            await event.send(
                MessageChain().message(
                    t("msg-d7a36c19"),
                ),
            )
            return

        # 兼容 reset scene 的专门配置
        cmd_name = token.get(1)
        cmd_type = token.get(2)

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
            await event.send(MessageChain().message(t("msg-afe0fa58", config_menu=config_menu)))
            return

        if cmd_name == "reset" and cmd_type == "scene" and token.len >= 4:
            scene_num = token.get(3)
            perm_type = token.get(4)

            if scene_num is None or perm_type is None:
                await event.send(MessageChain().message(t("msg-0c85d498")))
                return

            if not scene_num.isdigit() or int(scene_num) < 1 or int(scene_num) > 3:
                await event.send(
                    MessageChain().message(t("msg-4e0afcd1")),
                )
                return

            if perm_type not in ["admin", "member"]:
                await event.send(
                    MessageChain().message(t("msg-830d6eb8")),
                )
                return

            scene_num = int(scene_num)
            scene = RstScene.from_index(scene_num)
            scene_key = scene.key

            await self.update_reset_permission(scene_key, perm_type)

            await event.send(
                MessageChain().message(
                    t("msg-d1180ead", res=scene.name, perm_type=perm_type),
                ),
            )
            return

        if cmd_type not in ["admin", "member"]:
            await event.send(
                MessageChain().message(t("msg-8d9bc364")),
            )
            return

        # 查找指令
        cmd_name = " ".join(token.tokens[1:-1])
        cmd_type = token.get(-1)
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
            await event.send(MessageChain().message(t("msg-1f2f65e0")))
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
                    from astrbot.api.event import filter

                    filter_.permission_type = filter.PermissionType.ADMIN
                else:
                    from astrbot.api.event import filter

                    filter_.permission_type = filter.PermissionType.MEMBER
                found_permission_filter = True
                break
        if not found_permission_filter:
            from astrbot.api.event import filter

            found_command.event_filters.insert(
                0,
                PermissionTypeFilter(
                    filter.PermissionType.ADMIN
                    if cmd_type == "admin"
                    else filter.PermissionType.MEMBER,
                ),
            )
        cmd_group_str = "指令组" if cmd_group else "指令"
        await event.send(
            MessageChain().message(
                t("msg-cd271581", cmd_name=cmd_name, cmd_group_str=cmd_group_str, cmd_type=cmd_type),
            ),
        )
