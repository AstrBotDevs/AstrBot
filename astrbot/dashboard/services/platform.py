import inspect
import os

from quart import request

from astrbot.core import file_token_service, logger
from astrbot.core.platform.register import platform_cls_map

from ..entities import Response
from . import BaseService
from .utils import save_config


class PlatformService(BaseService):
    def __init__(self, core_lifecycle):
        super().__init__(core_lifecycle)
        self._logo_token_cache = {}  # 缓存logo token，避免重复注册

    async def get_platform_list(self):
        """获取所有平台的列表"""
        platform_list = []
        config = self.cl.astrbot_config
        for platform in config["platform"]:
            platform_list.append(platform)
        return Response().ok({"platforms": platform_list}).__dict__

    async def post_new_platform(self):
        """创建新的平台配置"""
        new_platform_config = await request.json

        # 如果是支持统一 webhook 模式的平台，生成 webhook_uuid
        from astrbot.core.utils.webhook_utils import ensure_platform_webhook_config

        ensure_platform_webhook_config(new_platform_config)

        config = self.cl.astrbot_config
        config["platform"].append(new_platform_config)
        try:
            save_config(config, config, is_core=True)
            await self.cl.platform_manager.load_platform(new_platform_config)
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "新增平台配置成功~").__dict__

    async def post_update_platform(self):
        """更新平台配置"""
        update_platform_config = await request.json
        origin_platform_id = update_platform_config.get("id", None)
        new_config = update_platform_config.get("config", None)
        if not origin_platform_id or not new_config:
            return Response().error("参数错误").__dict__

        if origin_platform_id != new_config.get("id", None):
            return Response().error("机器人名称不允许修改").__dict__

        # 如果是支持统一 webhook 模式的平台，且启用了统一 webhook 模式，确保有 webhook_uuid
        from astrbot.core.utils.webhook_utils import ensure_platform_webhook_config

        ensure_platform_webhook_config(new_config)

        config = self.cl.astrbot_config
        for i, platform in enumerate(config["platform"]):
            if platform["id"] == origin_platform_id:
                config["platform"][i] = new_config
                break
        else:
            return Response().error("未找到对应平台").__dict__

        try:
            save_config(config, config, is_core=True)
            await self.cl.platform_manager.reload(new_config)
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "更新平台配置成功~").__dict__

    async def post_delete_platform(self):
        """删除平台配置"""
        platform_id = await request.json
        platform_id = platform_id.get("id")
        config = self.cl.astrbot_config
        for i, platform in enumerate(config["platform"]):
            if platform["id"] == platform_id:
                del config["platform"][i]
                break
        else:
            return Response().error("未找到对应平台").__dict__
        try:
            save_config(config, config, is_core=True)
            await self.cl.platform_manager.terminate_platform(platform_id)
        except Exception as e:
            return Response().error(str(e)).__dict__
        return Response().ok(None, "删除平台配置成功~").__dict__

    async def register_platform_logo(self, platform, platform_default_tmpl):
        """注册平台logo文件并生成访问令牌"""
        if not platform.logo_path:
            return

        try:
            # 检查缓存
            cache_key = f"{platform.name}:{platform.logo_path}"
            if cache_key in self._logo_token_cache:
                cached_token = self._logo_token_cache[cache_key]
                # 确保platform_default_tmpl[platform.name]存在且为字典
                if platform.name not in platform_default_tmpl or not isinstance(
                    platform_default_tmpl[platform.name], dict
                ):
                    platform_default_tmpl[platform.name] = {}
                platform_default_tmpl[platform.name]["logo_token"] = cached_token
                logger.debug(f"Using cached logo token for platform {platform.name}")
                return

            # 获取平台适配器类
            platform_cls = platform_cls_map.get(platform.name)
            if not platform_cls:
                logger.warning(f"Platform class not found for {platform.name}")
                return

            # 获取插件目录路径
            module_file = inspect.getfile(platform_cls)
            plugin_dir = os.path.dirname(module_file)

            # 解析logo文件路径
            logo_file_path = os.path.join(plugin_dir, platform.logo_path)

            # 检查文件是否存在并注册令牌
            if os.path.exists(logo_file_path):
                logo_token = await file_token_service.register_file(
                    logo_file_path,
                    timeout=3600,
                )

                # 确保platform_default_tmpl[platform.name]存在且为字典
                if platform.name not in platform_default_tmpl or not isinstance(
                    platform_default_tmpl[platform.name], dict
                ):
                    platform_default_tmpl[platform.name] = {}

                platform_default_tmpl[platform.name]["logo_token"] = logo_token

                # 缓存token
                self._logo_token_cache[cache_key] = logo_token

                logger.debug(f"Logo token registered for platform {platform.name}")
            else:
                logger.warning(
                    f"Platform {platform.name} logo file not found: {logo_file_path}",
                )

        except (ImportError, AttributeError) as e:
            logger.warning(
                f"Failed to import required modules for platform {platform.name}: {e}",
            )
        except OSError as e:
            logger.warning(f"File system error for platform {platform.name} logo: {e}")
        except Exception as e:
            logger.warning(
                f"Unexpected error registering logo for platform {platform.name}: {e}",
            )
