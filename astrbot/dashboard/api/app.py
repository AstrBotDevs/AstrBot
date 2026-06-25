# 启用 Python 的延迟注解求值特性（PEP 563），允许在类型注解中使用尚未定义的类型名称
from __future__ import annotations

# 从 types 模块导入 SimpleNamespace，用于创建简单的命名空间对象，可以用点号访问属性
from types import SimpleNamespace

# 从 fastapi 导入核心类：FastAPI 应用实例、HTTPException 异常类、Request 请求对象
from fastapi import FastAPI, HTTPException, Request
# 从 fastapi.responses 导入 JSONResponse，用于返回 JSON 格式的响应
from fastapi.responses import JSONResponse

# 导入核心模块：日志代理器，用于收集和分发日志消息
from astrbot.core import LogBroker
# 导入核心生命周期管理器，统筹整个 AstrBot 的启动、运行和关闭流程
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
# 导入数据库抽象基类，定义统一的数据库操作接口
from astrbot.core.db import BaseDatabase
# 导入 API 响应工具：ApiError 自定义异常类和 error 响应构造辅助函数
from astrbot.dashboard.responses import ApiError, error

# 以下是一系列服务层的导入，每个服务封装了特定业务逻辑，供路由层调用
# API 密钥管理服务，处理 API 密钥的增删改查
from astrbot.dashboard.services.api_key_service import ApiKeyService
# 认证服务，处理用户登录、JWT 令牌生成与验证
from astrbot.dashboard.services.auth_service import AuthService
# 备份服务，管理系统配置和数据的备份与恢复
from astrbot.dashboard.services.backup_service import BackupService
# 聊天服务，处理聊天消息的收发逻辑
from astrbot.dashboard.services.chat_service import ChatService
# ChatUI 项目服务，管理前端聊天界面的项目配置
from astrbot.dashboard.services.chatui_project_service import ChatUIProjectService
# 命令服务，管理系统中的自定义命令
from astrbot.dashboard.services.command_service import CommandService
# 配置相关服务的分组导入：
# Bot 配置服务，管理机器人实例的配置
from astrbot.dashboard.services.config_service import (
    BotConfigService,
    ConfigDisplayService,   # 配置展示服务，格式化配置信息供前端展示
    ConfigFileService,      # 配置文件服务，管理配置文件读写
    ConfigProfileService,   # 配置概要服务，管理多套配置方案
    ConfigRoutingService,   # 配置路由服务，管理配置与路由的映射
    ProviderConfigService,  # 提供者配置服务，管理 LLM 提供商的配置
)
# 对话服务，管理聊天对话的创建、历史记录等
from astrbot.dashboard.services.conversation_service import ConversationService
# 定时任务服务，管理系统中的 cron 定时任务
from astrbot.dashboard.services.cron_service import CronService
# 文件服务，处理文件上传、下载等操作
from astrbot.dashboard.services.file_service import FileService
# 知识库服务，管理 RAG 知识库的文档和检索
from astrbot.dashboard.services.knowledge_base_service import KnowledgeBaseService
# 实时聊天服务，管理基于 WebSocket 的实时对话
from astrbot.dashboard.services.live_chat_service import LiveChatService
# 日志服务，提供日志查询和流式推送功能
from astrbot.dashboard.services.log_service import LogService
# OpenAPI 服务，管理对外 API 的配置和调用
from astrbot.dashboard.services.open_api_service import OpenApiService
# 人格服务，管理 AI 回复的角色设定（人设）
from astrbot.dashboard.services.persona_service import PersonaService
# 平台服务，管理机器人接入的不同消息平台（如 QQ、微信等）
from astrbot.dashboard.services.platform_service import PlatformService
# 插件页面服务，管理插件提供的自定义前端页面
from astrbot.dashboard.services.plugin_page_service import PluginPageService
# 插件服务，管理插件的安装、卸载、启用、禁用等生命周期
from astrbot.dashboard.services.plugin_service import PluginService
# 会话管理服务，管理用户与机器人的会话状态
from astrbot.dashboard.services.session_management_service import (
    SessionManagementService,
)
# 技能服务，管理 AI 可调用的技能和工具
from astrbot.dashboard.services.skills_service import SkillsService
# 统计服务，提供系统使用数据的统计和汇总
from astrbot.dashboard.services.stat_service import StatService
# 子智能体服务，管理子 AI 代理的配置和运行
from astrbot.dashboard.services.subagent_service import SubAgentService
# 文本转图片服务，管理文本转图片的相关功能
from astrbot.dashboard.services.t2i_service import T2iService
# 工具服务，管理可供 AI 调用的外部工具
from astrbot.dashboard.services.tools_service import ToolsService
# 更新服务，管理系统和控制面板的版本更新
from astrbot.dashboard.services.update_service import (
    DEMO_MODE,                   # 演示模式标志，控制是否启用演示限制
    UpdateService,               # 更新服务主类
    call_download_dashboard,     # 下载控制面板静态文件的函数
    call_extract_dashboard,      # 解压控制面板文件的函数
    call_get_dashboard_version,  # 获取当前控制面板版本的函数
    call_pip_install,           # 执行 pip 安装命令的函数
)

# 从当前包导入各个路由模块的 legacy 路由器（用于兼容旧版 API 路径）
# 每个 legacy_router 包含了对应模块的旧版路由规则
from .api_keys import legacy_router as legacy_api_keys_router
from .auth import legacy_router as legacy_auth_router
from .backups import legacy_router as legacy_backups_router
from .bots import legacy_router as legacy_bots_router
from .chat import legacy_router as legacy_chat_router
from .chat_projects import legacy_router as legacy_chat_projects_router
from .config_profiles import legacy_router as legacy_config_profiles_router
from .conversations import legacy_router as legacy_conversations_router
from .cron import legacy_router as legacy_cron_router
from .extensions import legacy_router as legacy_extensions_router
from .files import legacy_router as legacy_files_router
from .knowledge_bases import legacy_router as legacy_knowledge_bases_router
from .live_chat import legacy_router as legacy_live_chat_router
from .logs import legacy_router as legacy_logs_router
from .personas import legacy_router as legacy_personas_router
from .platform import legacy_router as legacy_platform_router
from .plugins import legacy_router as legacy_plugins_router
from .providers import legacy_router as legacy_providers_router
# 从 router 模块导入 API 版本前缀常量和用于构建新 API 路由器的工厂函数
from .router import API_V1_PREFIX, build_api_router
from .sessions import legacy_router as legacy_sessions_router
from .skills import legacy_router as legacy_skills_router
# 导入静态文件路由器，负责提供控制面板的前端静态资源
from .static_files import router as static_files_router
from .stats import legacy_router as legacy_stats_router
from .subagents import legacy_router as legacy_subagents_router
from .t2i import legacy_router as legacy_t2i_router
from .tools import legacy_router as legacy_tools_router
from .updates import legacy_router as legacy_updates_router

# 定义清空站点数据的响应头，用于通知浏览器清除缓存（'cache' 表示清除所有缓存数据）
CLEAR_SITE_DATA_HEADERS = {"Clear-Site-Data": '"cache"'}


# 工厂函数：创建并配置整个控制面板的 ASGI 应用实例
def create_dashboard_asgi_app(
    *,
    # 核心生命周期管理器，提供对整个 AstrBot 运行状态的访问和控制
    core_lifecycle: AstrBotCoreLifecycle,
    # 数据库实例，用于持久化存储各类业务数据
    db: BaseDatabase,
    # JWT 签名密钥，用于生成和验证认证令牌
    jwt_secret: str,
    # 控制面板静态文件夹的路径，如果不提供则不启用静态文件服务
    static_folder: str | None = None,
) -> FastAPI:
    # 创建 FastAPI 应用实例，并配置 OpenAPI 文档相关参数
    app = FastAPI(
        title="AstrBot OpenAPI",         # API 文档标题
        version="1.0.0",                 # API 版本号
        openapi_url=f"{API_V1_PREFIX}/openapi.json",  # OpenAPI JSON 规范文档的访问地址
        docs_url=f"{API_V1_PREFIX}/docs",             # Swagger UI 文档页面的访问地址
        redoc_url=f"{API_V1_PREFIX}/redoc",           # ReDoc 文档页面的访问地址
    )
    # 将核心组件挂载到 app.state 上，供所有路由和服务通过 request.app.state 访问
    # 存储核心生命周期管理器
    app.state.core_lifecycle = core_lifecycle
    # 存储数据库实例
    app.state.db = db
    # 存储 JWT 密钥，供认证中间件和路由使用
    app.state.jwt_secret = jwt_secret
    # 存储静态文件夹路径，供静态文件路由器使用
    app.state.dashboard_static_folder = static_folder
    # 获取或创建日志代理器实例，用于日志的收集和分发
    log_broker = getattr(core_lifecycle, "log_broker", None) or LogBroker()
    # 使用 SimpleNamespace 创建服务容器，将所有业务服务以属性方式组织在一起
    app.state.services = SimpleNamespace(
        # 配置方案服务：管理多套配置的切换和保存
        config_profiles=ConfigProfileService(core_lifecycle, db),
        # 配置展示服务：格式化配置数据供前端展示
        config_display=ConfigDisplayService(core_lifecycle),
        # 配置文件服务：处理配置文件（如 YAML/JSON）的读写操作
        config_files=ConfigFileService(core_lifecycle),
        # 配置路由服务：管理消息路由规则的配置
        config_routes=ConfigRoutingService(core_lifecycle),
        # API 密钥服务：管理用于外部调用的 API Key
        api_keys=ApiKeyService(db),
        # 认证服务：处理用户登录和 JWT 令牌
        auth=AuthService(db, core_lifecycle.astrbot_config),
        # 备份服务：管理系统数据的备份与恢复
        backups=BackupService(db, core_lifecycle),
        # 聊天服务：处理 AI 对话的核心逻辑
        chat=ChatService(db, core_lifecycle),
        # ChatUI 项目服务：管理前端聊天界面的项目配置
        chat_projects=ChatUIProjectService(db),
        # 命令服务：管理自定义命令的注册和执行
        commands=CommandService(core_lifecycle.astrbot_config, core_lifecycle),
        # 对话服务：管理对话会话的创建和历史
        conversations=ConversationService(db, core_lifecycle),
        # 定时任务服务：管理 cron 定时任务的增删改
        cron=CronService(core_lifecycle),
        # 文件服务：处理文件的上传和下载
        files=FileService(),
        # 知识库服务：管理知识库文档和向量检索
        knowledge_bases=KnowledgeBaseService(core_lifecycle),
        # 实时聊天服务：管理 WebSocket 连接和实时消息推送
        live_chat=LiveChatService(db, core_lifecycle),
        # 日志服务：提供日志查询和流式推送
        logs=LogService(log_broker, core_lifecycle.astrbot_config),
        # Bot 配置服务：管理机器人实例的配置参数
        bots=BotConfigService(core_lifecycle),
        # 平台服务：管理接入的消息平台
        platforms=PlatformService(core_lifecycle),
        # 提供者配置服务：管理 LLM 提供商的 API 配置
        providers=ProviderConfigService(core_lifecycle),
        # 人格服务：管理 AI 回复的人设和角色
        personas=PersonaService(core_lifecycle),
        # 插件服务：管理插件的生命周期
        plugins=PluginService(core_lifecycle, core_lifecycle.plugin_manager),
        # 插件页面服务：管理插件提供的自定义网页
        plugin_pages=PluginPageService(
            core_lifecycle.plugin_manager,
            core_lifecycle=core_lifecycle,  # 显式传递核心生命周期引用
        ),
        # OpenAPI 服务：管理对外 API 的配置
        open_api=OpenApiService(db, core_lifecycle),
        # 会话管理服务：管理用户与机器人的交互会话
        sessions=SessionManagementService(core_lifecycle, db),
        # 技能服务：管理 AI 可调用的技能
        skills=SkillsService(core_lifecycle),
        # 统计服务：收集和汇总系统运行数据
        stats=StatService(db, core_lifecycle, core_lifecycle.astrbot_config),
        # 子智能体服务：管理子 AI 代理
        subagents=SubAgentService(core_lifecycle),
        # 文本转图片服务：管理文字转图片的渲染
        t2i=T2iService(core_lifecycle),
        # 工具服务：管理外部工具的定义和调用
        tools=ToolsService(core_lifecycle),
        # 更新服务：管理系统版本更新
        updates=UpdateService(
            core_lifecycle.astrbot_updator,   # 更新器实例
            core_lifecycle,                    # 核心生命周期引用
            download_dashboard_func=call_download_dashboard,    # 下载控制面板的回调函数
            extract_dashboard_func=call_extract_dashboard,      # 解压控制面板的回调函数
            get_dashboard_version_func=call_get_dashboard_version,  # 获取版本的回调函数
            pip_install_func=call_pip_install,                  # pip 安装的回调函数
            demo_mode=DEMO_MODE,                # 是否为演示模式
            clear_site_data_headers=CLEAR_SITE_DATA_HEADERS,  # 清除缓存的响应头
        ),
    )

    # 注册全局异常处理器：捕获并处理 ApiError 自定义异常
    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError):
        # 返回 JSON 格式的错误响应，状态码由异常对象提供
        return JSONResponse(
            error(exc.message, exc.data),   # 使用 error 辅助函数构造标准错误响应体
            status_code=exc.status_code,
        )

    # 注册全局异常处理器：捕获并处理 ValueError 异常（通常表示参数验证失败）
    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        # 返回 400 Bad Request 错误，消息为异常的描述信息
        return JSONResponse(error(str(exc)), status_code=400)

    # 注册全局异常处理器：捕获并处理 FastAPI 内置的 HTTPException 异常
    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException):
        # 提取异常中的详细信息，如果是字符串则直接使用，否则使用默认消息
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        # 返回相应状态码的 JSON 错误响应
        return JSONResponse(error(detail), status_code=exc.status_code)

    # Legacy dashboard routes keep old /api/* callers working without entering OpenAPI.
    # 将各个旧版路由器注册到应用中，保持向后兼容，使得旧版 /api/* 路径请求仍然有效
    app.include_router(legacy_api_keys_router)          # API 密钥管理相关路由
    app.include_router(legacy_auth_router)              # 认证相关路由
    app.include_router(legacy_backups_router)           # 备份相关路由
    app.include_router(legacy_config_profiles_router)   # 配置方案相关路由
    app.include_router(legacy_bots_router)              # 机器人配置相关路由
    app.include_router(legacy_providers_router)         # 提供者配置相关路由
    app.include_router(legacy_chat_router)              # 聊天相关路由
    app.include_router(legacy_chat_projects_router)     # ChatUI 项目相关路由
    app.include_router(legacy_conversations_router)     # 对话管理相关路由
    app.include_router(legacy_cron_router)              # 定时任务相关路由
    app.include_router(legacy_extensions_router)        # 扩展相关路由
    app.include_router(legacy_files_router)             # 文件管理相关路由
    app.include_router(legacy_knowledge_bases_router)   # 知识库相关路由
    app.include_router(legacy_live_chat_router)         # 实时聊天相关路由
    app.include_router(legacy_logs_router)              # 日志相关路由
    app.include_router(legacy_sessions_router)          # 会话管理相关路由
    app.include_router(legacy_skills_router)            # 技能相关路由
    app.include_router(legacy_stats_router)             # 统计相关路由
    app.include_router(legacy_subagents_router)         # 子智能体相关路由
    app.include_router(legacy_tools_router)             # 工具相关路由
    app.include_router(legacy_platform_router)          # 平台相关路由
    app.include_router(legacy_plugins_router)           # 插件相关路由
    app.include_router(legacy_t2i_router)               # 文本转图片相关路由
    app.include_router(legacy_personas_router)          # 人格管理相关路由
    app.include_router(legacy_updates_router)           # 系统更新相关路由
    # 注册新版本 API 路由器（基于 OpenAPI 规范的标准化路由）
    app.include_router(build_api_router())
    # 注册静态文件路由器，负责提供控制面板的前端页面和资源
    app.include_router(static_files_router)
    # 返回配置完成的 FastAPI 应用实例
    return app