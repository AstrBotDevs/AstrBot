"""插件上下文兼容层。

此模块提供旧版 Context 类的向后兼容导入。
Context 是插件运行时的核心接口，提供：

- llm_generate(): 调用 LLM 生成文本
- tool_loop_agent(): 运行 LLM Agent 循环
- send_message(): 发送消息到会话
- conversation_manager: 会话管理器
- put_kv_data()/get_kv_data()/delete_kv_data(): 键值存储

迁移说明：
- 旧版: from astrbot_sdk.api.star import Context
- 新版: from astrbot_sdk import Context (astrbot_sdk.context.Context)

新版 Context 提供更丰富的接口：
- ctx.llm.chat_raw(): LLM 调用
- ctx.platform.send(): 发送消息
- ctx.db.set()/get()/delete(): 数据存储

注意：使用旧版 API 会触发弃用警告。
"""

from ..._legacy_api import Context

__all__ = ["Context"]
