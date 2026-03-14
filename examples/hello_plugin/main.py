from astrbot_sdk import Context, MessageEvent, Star, on_command


class HelloPlugin(Star):
    @on_command("hello", description="发送最小问候")
    async def hello(self, event: MessageEvent, ctx: Context) -> None:
        await event.reply("Hello, World!")

    @on_command("about", description="返回当前插件信息")
    async def about(self, event: MessageEvent, ctx: Context) -> None:
        plugin = await ctx.metadata.get_current_plugin()
        display_name = plugin.display_name if plugin is not None else ctx.plugin_id
        await event.reply(f"我是 {display_name}")
