import astrbot.api.star as star
import astrbot.api.event.filter as filter
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api import logger
from astrbot.core.star.star_tools import StarTools


class Main(star.Star):
    async def initialize(self):
        logger.info("astrbot-filefield-demo initialized")

    @filter.command("ffdemo")
    async def show_file_info(self, event: AstrMessageEvent):
        """展示配置中文件字段的当前值，并尝试读取文件大小。使用 /ffdemo 触发"""
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        rel = cfg.get("custom_vocabulary", "")
        if not rel:
            event.set_result(
                MessageEventResult().message("尚未配置 custom_vocabulary 的文件。请在面板上传并设为当前。")
            )
            return

        try:
            data_dir = StarTools.get_data_dir()  # 当前插件的数据目录
            path = (data_dir / rel).resolve()
            size = path.stat().st_size if path.exists() else -1
            msg = f"当前文件相对路径: {rel}\n绝对路径: {str(path)}\n大小: {size} bytes"
        except Exception as e:
            msg = f"读取文件信息失败: {e}"

        event.set_result(MessageEventResult().message(msg))

