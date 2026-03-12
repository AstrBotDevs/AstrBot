"""AstrBot SDK 公共 API 模块。

此模块提供插件开发所需的公共接口，包括：
- components: 命令组件基类
- event: 事件处理相关工具（过滤器、事件类）
- star: 插件上下文

注意：大部分 API 是为了兼容旧版插件而保留的兼容层。
新版 API 请参考 astrbot_sdk.context.Context 和 astrbot_sdk.decorators 模块。

# TODO: 相比旧版 API (src/astrbot_sdk/api)，新版缺少以下模块：

## 1. basic/ 模块 (完全缺失)
旧版路径: src/astrbot_sdk/api/basic/
- AstrBotConfig: AstrBot 配置类，继承自 dict
- BaseConversationManager: 会话管理基类，提供以下方法：
  - new_conversation(): 新建对话
  - switch_conversation(): 切换对话
  - delete_conversation(): 删除对话
  - get_curr_conversation_id(): 获取当前对话 ID
  - get_conversation(): 获取对话
  - get_conversations(): 获取对话列表
  - get_filtered_conversations(): 获取过滤后的对话列表
  - update_conversation(): 更新对话
  - add_message_pair(): 添加消息对
  - get_human_readable_context(): 获取人类可读上下文
- Conversation: 对话实体数据类 (platform_id, user_id, cid, history, title, persona_id, created_at, updated_at)

## 2. message/ 模块 (完全缺失)
旧版路径: src/astrbot_sdk/api/message/
- MessageChain: 消息链类，提供链式 API：
  - message(): 添加文本
  - at(): 添加 @ 提及
  - at_all(): 添加 @ 全体成员
  - url_image(): 添加网络图片
  - file_image(): 添加本地图片
  - base64_image(): 添加 base64 图片
  - use_t2i(): 设置文本转图片
  - get_plain_text(): 获取纯文本
  - squash_plain(): 合并文本段
- 消息组件类 (components.py):
  - Plain, Image, Record, Video, File (基础类型)
  - At, AtAll, Reply, Face, Node, Nodes (IM 类型)
  - Share, Contact, Location, Music, Poke, Forward, Json, WechatEmoji 等
  - ComponentType 枚举, BaseMessageComponent 基类

## 3. event/ 模块 (部分缺失)
旧版路径: src/astrbot_sdk/api/event/
已有:
- filter.py (简化版): command, regex, permission 装饰器
缺失:
- astrbot_message.py:
  - MessageMember: 消息成员数据类 (user_id, nickname)
  - Group: 群组数据类 (group_id, group_name, group_avatar, group_owner, group_admins, members)
  - AstrBotMessage: AstrBot 消息对象 (type, self_id, session_id, message_id, sender, message, message_str, raw_message, timestamp, group)
- astr_message_event.py:
  - AstrMessageEvent: 消息事件类，核心方法：
    - get_platform_name/id(), get_message_str/messages/type()
    - get_session_id/group_id/self_id/sender_id/sender_name()
    - set_extra/get_extra/clear_extra()
    - is_private_chat/is_wake_up/is_admin()
    - set_result/stop_event/continue_event/is_stopped()
    - make_result/plain_result/image_result/chain_result()
    - send(), react(), get_group()
  - AstrMessageEventModel: Pydantic 模型版本
- event_result.py:
  - EventResultType: 事件结果类型枚举 (CONTINUE, STOP)
  - ResultContentType: 结果内容类型枚举 (LLM_RESULT, GENERAL_RESULT, STREAMING_RESULT, STREAMING_FINISH)
  - MessageEventResult: 消息事件结果类，继承 MessageChain
- event_type.py:
  - EventType: 内部事件类型枚举 (OnAstrBotLoadedEvent, OnPlatformLoadedEvent, AdapterMessageEvent, OnLLMRequestEvent, OnLLMResponseEvent, OnDecoratingResultEvent, OnCallingFuncToolEvent, OnAfterMessageSentEvent)
- message_session.py:
  - MessageSession: 消息会话标识类 (platform_name, message_type, session_id)
- message_type.py:
  - MessageType: 消息类型枚举 (GROUP_MESSAGE, FRIEND_MESSAGE, OTHER_MESSAGE)

## 4. platform/ 模块 (完全缺失)
旧版路径: src/astrbot_sdk/api/platform/
- PlatformMetadata: 平台元数据类 (name, description, id, default_config_tmpl, adapter_display_name, logo_path)

## 5. provider/ 模块 (完全缺失)
旧版路径: src/astrbot_sdk/api/provider/
- LLMResponse: LLM 响应数据类
  - role, result_chain, tools_call_args/tools_call_name/tools_call_ids
  - raw_completion (支持 OpenAI/Anthropic/Google 格式)
  - to_openai_tool_calls(), to_openai_to_calls_model()

## 6. star/ 模块 (部分缺失)
旧版路径: src/astrbot_sdk/api/star/
已有:
- context.py (兼容层): Context 类
缺失:
- star.py:
  - StarMetadata: 插件元数据类 (name, author, desc, version, repo, module_path, root_dir_name, reserved, activated, config, star_handler_full_names, display_name, logo_path)

## 7. components/ 模块 (部分缺失)
旧版路径: src/astrbot_sdk/api/components/
已有:
- command.py: CommandComponent 兼容层
缺失: (无其他文件，旧版也只有 command.py)

## 8. filter.py 装饰器 (部分缺失)
旧版 filter.py 导出的装饰器:
已有: command, regex, permission
缺失:
- custom_filter: 自定义过滤器
- event_message_type: 事件消息类型
- platform_adapter_type: 平台适配器类型
- after_message_sent: 消息发送后钩子
- on_astrbot_loaded: AstrBot 加载完成钩子
- on_platform_loaded: 平台加载完成钩子
- on_decorating_result: 结果装饰钩子
- on_llm_request: LLM 请求钩子
- on_llm_response: LLM 响应钩子
- command_group: 命令组
- llm_tool: LLM 工具注册 (已注释)

旧版还导出:
- CustomFilter, EventMessageType, EventMessageTypeFilter
- PermissionType, PermissionTypeFilter
- PlatformAdapterType, PlatformAdapterTypeFilter
"""

__all__: list[str] = []
