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

# TODO: 相比旧版 star 模块，新版缺少以下内容：

## 缺失的文件：
1. star.py:
   - StarMetadata: 插件元数据类
     - name, author, desc, version, repo: 基础信息
     - module_path, root_dir_name: 模块路径信息
     - reserved, activated: 状态标志
     - config: AstrBotConfig 插件配置
     - star_handler_full_names: Handler 全名列表
     - display_name, logo_path: 展示信息

## 缺失的导入（旧版 star/__init__.py 为空）：
旧版 star 模块主要通过 context.py 提供 Context 类，
新版通过兼容层导入，但缺少 StarMetadata 的公开导出。
"""

from ..._legacy_api import Context

__all__ = ["Context"]
