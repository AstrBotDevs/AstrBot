import traceback
import asyncio
from astrbot.core.config.astrbot_config import AstrBotConfig
from .platform import Platform
from typing import List
from asyncio import Queue
from .register import platform_cls_map
from astrbot.core import logger
from .sources.webchat.webchat_adapter import WebChatAdapter


class PlatformManager:
    def __init__(self, config: AstrBotConfig, event_queue: Queue):
        self.platform_insts: List[Platform] = []
        """加载的 Platform 的实例"""

        self._inst_map = {}

        self.platforms_config = config["platform"]
        self.settings = config["platform_settings"]
        self.event_queue = event_queue

    async def initialize(self):
        """初始化所有平台适配器"""
        for platform in self.platforms_config:
            try:
                await self.load_platform(platform)
            except Exception as e:
                logger.error(f"初始化 {platform} 平台适配器失败: {e}")

        # 网页聊天
        webchat_inst = WebChatAdapter({}, self.settings, self.event_queue)
        self.platform_insts.append(webchat_inst)
        asyncio.create_task(
            self._task_wrapper(asyncio.create_task(webchat_inst.run(), name="webchat"))
        )

    async def load_platform(self, platform_config: dict):
        """实例化一个平台"""
        # 动态导入
        try:
            if not platform_config["enable"]:
                return

            logger.info(
                f"载入 {platform_config['type']}({platform_config['id']}) 平台适配器 ..."
            )
            match platform_config["type"]:
                case "aiocqhttp":
                    from .sources.aiocqhttp.aiocqhttp_platform_adapter import (
                        AiocqhttpAdapter,  # noqa: F401
                    )
                case "qq_official":
                    from .sources.qqofficial.qqofficial_platform_adapter import (
                        QQOfficialPlatformAdapter,  # noqa: F401
                    )
                case "qq_official_webhook":
                    from .sources.qqofficial_webhook.qo_webhook_adapter import (
                        QQOfficialWebhookPlatformAdapter,  # noqa: F401
                    )
                case "gewechat":
                    from .sources.gewechat.gewechat_platform_adapter import (
                        GewechatPlatformAdapter,  # noqa: F401
                    )
                case "lark":
                    from .sources.lark.lark_adapter import LarkPlatformAdapter  # noqa: F401
                case "dingtalk":
                    from .sources.dingtalk.dingtalk_adapter import (
                        DingtalkPlatformAdapter,  # noqa: F401
                    )
                case "telegram":
                    from .sources.telegram.tg_adapter import TelegramPlatformAdapter  # noqa: F401
                case "wecom":
                    from .sources.wecom.wecom_adapter import WecomPlatformAdapter  # noqa: F401
                case "weixin_official_account":
                    from .sources.weixin_official_account.weixin_offacc_adapter import WeixinOfficialAccountPlatformAdapter # noqa
        except (ImportError, ModuleNotFoundError) as e:
            logger.error(
                f"加载平台适配器 {platform_config['type']} 失败，原因：{e}。请检查依赖库是否安装。提示：可以在 管理面板->控制台->安装Pip库 中安装依赖库。"
            )
        except Exception as e:
            logger.error(f"加载平台适配器 {platform_config['type']} 失败，原因：{e}。")

        if platform_config["type"] not in platform_cls_map:
            logger.error(
                f"未找到适用于 {platform_config['type']}({platform_config['id']}) 平台适配器，请检查是否已经安装或者名称填写错误"
            )
            return
        cls_type = platform_cls_map[platform_config["type"]]
        inst: Platform = cls_type(platform_config, self.settings, self.event_queue)
        self._inst_map[platform_config["id"]] = {
            "inst": inst,
            "client_id": inst.client_self_id,
        }
        self.platform_insts.append(inst)

        asyncio.create_task(
            self._task_wrapper(
                asyncio.create_task(
                    inst.run(),
                    name=f"platform_{platform_config['type']}_{platform_config['id']}",
                )
            )
        )

    async def _task_wrapper(self, task: asyncio.Task):
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"------- 任务 {task.get_name()} 发生错误: {e}")
            for line in traceback.format_exc().split("\n"):
                logger.error(f"|    {line}")
            logger.error("-------")

    async def reload(self, platform_config: dict):
        await self.terminate_platform(platform_config["id"])
        if platform_config["enable"]:
            await self.load_platform(platform_config)

        # 和配置文件保持同步
        config_ids = [provider["id"] for provider in self.platforms_config]
        for key in list(self._inst_map.keys()):
            if key not in config_ids:
                await self.terminate_platform(key)

    async def terminate_platform(self, platform_id: str):
        if platform_id in self._inst_map:
            logger.info(f"正在尝试终止 {platform_id} 平台适配器 ...")

            # client_id = self._inst_map.pop(platform_id, None)
            info = self._inst_map.pop(platform_id, None)
            client_id = info["client_id"]
            inst = info["inst"]
            try:
                self.platform_insts.remove(
                    next(
                        inst
                        for inst in self.platform_insts
                        if inst.client_self_id == client_id
                    )
                )
            except Exception:
                logger.warning(f"可能未完全移除 {platform_id} 平台适配器")

            if getattr(inst, "terminate", None):
                await inst.terminate()

    async def terminate(self):
        for inst in self.platform_insts:
            if getattr(inst, "terminate", None):
                await inst.terminate()

    def get_insts(self):
        return self.platform_insts
