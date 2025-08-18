import traceback

from quart import request

from astrbot.core import logger, sp
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.provider.entities import ProviderType
from astrbot.core.star.session_llm_manager import SessionServiceManager
from astrbot.core.star.session_plugin_manager import SessionPluginManager

from .route import Response, Route, RouteContext


class SessionManagementRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db_helper: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.routes = {
            "/session/list": ("GET", self.list_sessions),
            "/session/update_persona": ("POST", self.update_session_persona),
            "/session/update_provider": ("POST", self.update_session_provider),
            "/session/plugins": ("GET", self.get_session_plugins),
            "/session/update_plugin": ("POST", self.update_session_plugin),
            "/session/update_llm": ("POST", self.update_session_llm),
            "/session/update_tts": ("POST", self.update_session_tts),
            "/session/update_name": ("POST", self.update_session_name),
            "/session/update_status": ("POST", self.update_session_status),
        }
        self.conv_mgr = core_lifecycle.conversation_manager
        self.core_lifecycle = core_lifecycle
        self.register_routes()

    async def list_sessions(self):
        """获取所有会话的列表，包括 persona 和 provider 信息"""
        try:
            preferences = await sp.session_get(umo=None, key="sel_conv_id", default=[])
            session_conversations = {}
            for pref in preferences:
                session_conversations[pref.scope_id] = pref.value["val"]
            provider_manager = self.core_lifecycle.provider_manager
            persona_mgr = self.core_lifecycle.persona_mgr
            personas = persona_mgr.personas_v3

            sessions = []

            # 构建会话信息
            for session_id, conversation_id in session_conversations.items():
                session_info = {
                    "session_id": session_id,
                    "conversation_id": conversation_id,
                    "persona_id": None,
                    "chat_provider_id": None,
                    "stt_provider_id": None,
                    "tts_provider_id": None,
                    "session_enabled": SessionServiceManager.is_session_enabled(
                        session_id
                    ),
                    "llm_enabled": SessionServiceManager.is_llm_enabled_for_session(
                        session_id
                    ),
                    "tts_enabled": SessionServiceManager.is_tts_enabled_for_session(
                        session_id
                    ),
                    "platform": session_id.split(":")[0]
                    if ":" in session_id
                    else "unknown",
                    "message_type": session_id.split(":")[1]
                    if session_id.count(":") >= 1
                    else "unknown",
                    "session_name": SessionServiceManager.get_session_display_name(
                        session_id
                    ),
                    "session_raw_name": session_id.split(":")[2]
                    if session_id.count(":") >= 2
                    else session_id,
                }

                # 获取对话信息
                conversation = await self.conv_mgr.get_conversation(
                    unified_msg_origin=session_id, conversation_id=conversation_id
                )
                if conversation:
                    session_info["persona_id"] = conversation.persona_id

                    # 查找 persona 名称
                    if conversation.persona_id and conversation.persona_id != "[%None]":
                        for persona in personas:
                            if persona["name"] == conversation.persona_id:
                                session_info["persona_id"] = persona["name"]
                                break
                    elif conversation.persona_id == "[%None]":
                        session_info["persona_id"] = "无人格"
                    else:
                        # 使用默认人格
                        default_persona = persona_mgr.selected_default_persona_v3
                        if default_persona:
                            session_info["persona_id"] = default_persona["name"]

                # 获取 provider 信息
                provider_manager = self.core_lifecycle.provider_manager
                chat_provider = provider_manager.get_using_provider(
                    provider_type=ProviderType.CHAT_COMPLETION, umo=session_id
                )
                tts_provider = provider_manager.get_using_provider(
                    provider_type=ProviderType.TEXT_TO_SPEECH, umo=session_id
                )
                stt_provider = provider_manager.get_using_provider(
                    provider_type=ProviderType.SPEECH_TO_TEXT, umo=session_id
                )
                if chat_provider:
                    meta = chat_provider.meta()
                    session_info["chat_provider_id"] = meta.id
                if tts_provider:
                    meta = tts_provider.meta()
                    session_info["tts_provider_id"] = meta.id
                if stt_provider:
                    meta = stt_provider.meta()
                    session_info["stt_provider_id"] = meta.id

                sessions.append(session_info)

            # 获取可用的 personas 和 providers 列表
            available_personas = [
                {"name": p["name"], "prompt": p.get("prompt", "")} for p in personas
            ]

            available_chat_providers = []
            for provider in provider_manager.provider_insts:
                meta = provider.meta()
                available_chat_providers.append(
                    {
                        "id": meta.id,
                        "name": meta.id,
                        "model": meta.model,
                        "type": meta.type,
                    }
                )

            available_stt_providers = []
            for provider in provider_manager.stt_provider_insts:
                meta = provider.meta()
                available_stt_providers.append(
                    {
                        "id": meta.id,
                        "name": meta.id,
                        "model": meta.model,
                        "type": meta.type,
                    }
                )

            available_tts_providers = []
            for provider in provider_manager.tts_provider_insts:
                meta = provider.meta()
                available_tts_providers.append(
                    {
                        "id": meta.id,
                        "name": meta.id,
                        "model": meta.model,
                        "type": meta.type,
                    }
                )

            result = {
                "sessions": sessions,
                "available_personas": available_personas,
                "available_chat_providers": available_chat_providers,
                "available_stt_providers": available_stt_providers,
                "available_tts_providers": available_tts_providers,
            }

            return Response().ok(result).__dict__

        except Exception as e:
            error_msg = f"获取会话列表失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return Response().error(f"获取会话列表失败: {str(e)}").__dict__

    async def update_session_persona(self):
        """更新指定会话的 persona"""
        try:
            data = await request.get_json()
            session_id = data.get("session_id")
            persona_name = data.get("persona_name")

            if not session_id:
                return Response().error("缺少必要参数: session_id").__dict__

            if persona_name is None:
                return Response().error("缺少必要参数: persona_name").__dict__

            # 获取会话当前的对话 ID
            conversation_manager = self.core_lifecycle.star_context.conversation_manager
            conversation_id = await conversation_manager.get_curr_conversation_id(
                session_id
            )

            if not conversation_id:
                # 如果没有对话，创建一个新的对话
                conversation_id = await conversation_manager.new_conversation(
                    session_id
                )

            # 更新 persona
            await conversation_manager.update_conversation_persona_id(
                session_id, persona_name
            )

            return (
                Response()
                .ok({"message": f"成功更新会话 {session_id} 的人格为 {persona_name}"})
                .__dict__
            )

        except Exception as e:
            error_msg = f"更新会话人格失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return Response().error(f"更新会话人格失败: {str(e)}").__dict__

    async def update_session_provider(self):
        """更新指定会话的 provider"""
        try:
            data = await request.get_json()
            session_id = data.get("session_id")
            provider_id = data.get("provider_id")
            # "chat_completion", "speech_to_text", "text_to_speech"
            provider_type = data.get("provider_type")

            if not session_id or not provider_id or not provider_type:
                return (
                    Response()
                    .error("缺少必要参数: session_id, provider_id, provider_type")
                    .__dict__
                )

            # 转换 provider_type 字符串为枚举
            if provider_type == "chat_completion":
                provider_type_enum = ProviderType.CHAT_COMPLETION
            elif provider_type == "speech_to_text":
                provider_type_enum = ProviderType.SPEECH_TO_TEXT
            elif provider_type == "text_to_speech":
                provider_type_enum = ProviderType.TEXT_TO_SPEECH
            else:
                return (
                    Response()
                    .error(f"不支持的 provider_type: {provider_type}")
                    .__dict__
                )

            # 设置 provider
            provider_manager = self.core_lifecycle.star_context.provider_manager
            await provider_manager.set_provider(
                provider_id=provider_id,
                provider_type=provider_type_enum,
                umo=session_id,
            )

            return (
                Response()
                .ok(
                    {
                        "message": f"成功更新会话 {session_id} 的 {provider_type} 提供商为 {provider_id}"
                    }
                )
                .__dict__
            )

        except Exception as e:
            error_msg = f"更新会话提供商失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return Response().error(f"更新会话提供商失败: {str(e)}").__dict__

    async def get_session_plugins(self):
        """获取指定会话的插件配置信息"""
        try:
            session_id = request.args.get("session_id")

            if not session_id:
                return Response().error("缺少必要参数: session_id").__dict__

            # 获取所有已激活的插件
            all_plugins = []
            plugin_manager = self.core_lifecycle.plugin_manager

            for plugin in plugin_manager.context.get_all_stars():
                # 只显示已激活的插件，不包括保留插件
                if plugin.activated and not plugin.reserved:
                    plugin_name = plugin.name or ""
                    plugin_enabled = SessionPluginManager.is_plugin_enabled_for_session(
                        session_id, plugin_name
                    )

                    all_plugins.append(
                        {
                            "name": plugin_name,
                            "author": plugin.author,
                            "desc": plugin.desc,
                            "enabled": plugin_enabled,
                        }
                    )

            return (
                Response()
                .ok(
                    {
                        "session_id": session_id,
                        "plugins": all_plugins,
                    }
                )
                .__dict__
            )

        except Exception as e:
            error_msg = f"获取会话插件配置失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return Response().error(f"获取会话插件配置失败: {str(e)}").__dict__

    async def update_session_plugin(self):
        """更新指定会话的插件启停状态"""
        try:
            data = await request.get_json()
            session_id = data.get("session_id")
            plugin_name = data.get("plugin_name")
            enabled = data.get("enabled")

            if not session_id:
                return Response().error("缺少必要参数: session_id").__dict__

            if not plugin_name:
                return Response().error("缺少必要参数: plugin_name").__dict__

            if enabled is None:
                return Response().error("缺少必要参数: enabled").__dict__

            # 验证插件是否存在且已激活
            plugin_manager = self.core_lifecycle.plugin_manager
            plugin = plugin_manager.context.get_registered_star(plugin_name)

            if not plugin:
                return Response().error(f"插件 {plugin_name} 不存在").__dict__

            if not plugin.activated:
                return Response().error(f"插件 {plugin_name} 未激活").__dict__

            if plugin.reserved:
                return (
                    Response()
                    .error(f"插件 {plugin_name} 是系统保留插件，无法管理")
                    .__dict__
                )

            # 使用 SessionPluginManager 更新插件状态
            SessionPluginManager.set_plugin_status_for_session(
                session_id, plugin_name, enabled
            )

            return (
                Response()
                .ok(
                    {
                        "message": f"插件 {plugin_name} 已{'启用' if enabled else '禁用'}",
                        "session_id": session_id,
                        "plugin_name": plugin_name,
                        "enabled": enabled,
                    }
                )
                .__dict__
            )

        except Exception as e:
            error_msg = f"更新会话插件状态失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return Response().error(f"更新会话插件状态失败: {str(e)}").__dict__

    async def update_session_llm(self):
        """更新指定会话的LLM启停状态"""
        try:
            data = await request.get_json()
            session_id = data.get("session_id")
            enabled = data.get("enabled")

            if not session_id:
                return Response().error("缺少必要参数: session_id").__dict__

            if enabled is None:
                return Response().error("缺少必要参数: enabled").__dict__

            # 使用 SessionServiceManager 更新LLM状态
            SessionServiceManager.set_llm_status_for_session(session_id, enabled)

            return (
                Response()
                .ok(
                    {
                        "message": f"LLM已{'启用' if enabled else '禁用'}",
                        "session_id": session_id,
                        "llm_enabled": enabled,
                    }
                )
                .__dict__
            )

        except Exception as e:
            error_msg = f"更新会话LLM状态失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return Response().error(f"更新会话LLM状态失败: {str(e)}").__dict__

    async def update_session_tts(self):
        """更新指定会话的TTS启停状态"""
        try:
            data = await request.get_json()
            session_id = data.get("session_id")
            enabled = data.get("enabled")

            if not session_id:
                return Response().error("缺少必要参数: session_id").__dict__

            if enabled is None:
                return Response().error("缺少必要参数: enabled").__dict__

            # 使用 SessionServiceManager 更新TTS状态
            SessionServiceManager.set_tts_status_for_session(session_id, enabled)

            return (
                Response()
                .ok(
                    {
                        "message": f"TTS已{'启用' if enabled else '禁用'}",
                        "session_id": session_id,
                        "tts_enabled": enabled,
                    }
                )
                .__dict__
            )

        except Exception as e:
            error_msg = f"更新会话TTS状态失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return Response().error(f"更新会话TTS状态失败: {str(e)}").__dict__

    async def update_session_name(self):
        """更新指定会话的自定义名称"""
        try:
            data = await request.get_json()
            session_id = data.get("session_id")
            custom_name = data.get("custom_name", "")

            if not session_id:
                return Response().error("缺少必要参数: session_id").__dict__

            # 使用 SessionServiceManager 更新会话名称
            SessionServiceManager.set_session_custom_name(session_id, custom_name)

            return (
                Response()
                .ok(
                    {
                        "message": f"会话名称已更新为: {custom_name if custom_name.strip() else '已清除自定义名称'}",
                        "session_id": session_id,
                        "custom_name": custom_name,
                        "display_name": SessionServiceManager.get_session_display_name(
                            session_id
                        ),
                    }
                )
                .__dict__
            )

        except Exception as e:
            error_msg = f"更新会话名称失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return Response().error(f"更新会话名称失败: {str(e)}").__dict__

    async def update_session_status(self):
        """更新指定会话的整体启停状态"""
        try:
            data = await request.get_json()
            session_id = data.get("session_id")
            session_enabled = data.get("session_enabled")

            if not session_id:
                return Response().error("缺少必要参数: session_id").__dict__

            if session_enabled is None:
                return Response().error("缺少必要参数: session_enabled").__dict__

            # 使用 SessionServiceManager 更新会话整体状态
            SessionServiceManager.set_session_status(session_id, session_enabled)

            return (
                Response()
                .ok(
                    {
                        "message": f"会话整体状态已更新为: {'启用' if session_enabled else '禁用'}",
                        "session_id": session_id,
                        "session_enabled": session_enabled,
                    }
                )
                .__dict__
            )

        except Exception as e:
            error_msg = f"更新会话整体状态失败: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            return Response().error(f"更新会话整体状态失败: {str(e)}").__dict__
