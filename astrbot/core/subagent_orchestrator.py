# 导入未来版本的注解特性，允许在类型注解中使用前向引用
from __future__ import annotations

# 导入深拷贝模块，用于创建对象的完整副本
import copy
# TYPE_CHECKING 用于类型检查时的条件导入，避免运行时循环引用
from typing import TYPE_CHECKING, Any

# 从 astrbot 导入日志记录器
from astrbot import logger
# 导入 Agent 类，表示一个智能代理
from astrbot.core.agent.agent import Agent
# 导入 HandoffTool 类，用于创建代理间的任务移交工具
from astrbot.core.agent.handoff import HandoffTool
# 导入 FunctionToolManager 类，管理所有可用的函数工具
from astrbot.core.provider.func_tool_manager import FunctionToolManager

# 类型检查时的条件导入块
if TYPE_CHECKING:
    # 仅在类型检查时导入 PersonaManager，避免运行时依赖
    from astrbot.core.persona_mgr import PersonaManager


class SubAgentOrchestrator:
    """
    子代理编排器类
    
    作用：从配置中加载子代理定义，并注册移交工具。
    设计原则：此类本身不执行代理，执行通过 FunctionToolExecutor 中的 HandoffTool 完成。
    这是一个轻量级的编排层，负责配置管理和工具注册。
    """

    def __init__(
        self, tool_mgr: FunctionToolManager, persona_mgr: PersonaManager
    ) -> None:
        """
        初始化子代理编排器
        
        参数：
            tool_mgr: 函数工具管理器，用于注册和管理工具
            persona_mgr: 人设管理器，管理代理的角色和提示词
        """
        # 保存函数工具管理器实例
        self._tool_mgr = tool_mgr
        # 保存人设管理器实例
        self._persona_mgr = persona_mgr
        # 初始化移交工具列表，存储所有已注册的 HandoffTool
        self.handoffs: list[HandoffTool] = []

    async def reload_from_config(self, cfg: dict[str, Any]) -> None:
        """
        从配置字典重新加载子代理配置
        
        此方法会解析配置，创建 Agent 和 HandoffTool，并更新内部状态。
        
        参数：
            cfg: 包含子代理配置的字典，应包含 "agents" 键
        """
        # 导入 AstrAgentContext 类，用于 Agent 的类型参数
        from astrbot.core.astr_agent_context import AstrAgentContext

        # 从配置中获取代理列表，默认为空列表
        agents = cfg.get("agents", [])
        # 检查代理配置是否为列表类型，不是则记录警告并返回
        if not isinstance(agents, list):
            logger.warning("subagent_orchestrator.agents must be a list")
            return

        # 初始化移交工具列表，用于存储本次加载的工具
        handoffs: list[HandoffTool] = []
        # 遍历每个代理配置项
        for item in agents:
            # 跳过非字典类型的配置项
            if not isinstance(item, dict):
                continue
            # 检查代理是否启用（默认启用），未启用则跳过
            if not item.get("enabled", True):
                continue

            # 获取代理名称并去除首尾空格
            name = str(item.get("name", "")).strip()
            # 名称为空则跳过此代理
            if not name:
                continue

            # 获取人设 ID
            persona_id = item.get("persona_id")
            # 如果人设 ID 存在，转换为字符串并去除空格，空字符串转为 None
            if persona_id is not None:
                persona_id = str(persona_id).strip() or None
            # 通过人设 ID 获取人设数据
            persona_data = self._persona_mgr.get_persona_v3_by_id(persona_id)
            # 如果指定了人设但未找到对应数据，记录警告
            if persona_id and persona_data is None:
                logger.warning(
                    "SubAgent persona %s not found, fallback to inline prompt.",
                    persona_id,
                )

            # 获取系统提示词（指令），去除首尾空格
            instructions = str(item.get("system_prompt", "")).strip()
            # 获取公开描述，去除首尾空格
            public_description = str(item.get("public_description", "")).strip()
            # 获取提供商 ID
            provider_id = item.get("provider_id")
            # 如果提供商 ID 存在，转换为字符串并去除空格，空字符串转为 None
            if provider_id is not None:
                provider_id = str(provider_id).strip() or None
            # 获取工具列表配置
            tools = item.get("tools", [])
            # 初始化对话开始数据为 None
            begin_dialogs = None

            # 如果人设数据存在，使用人设数据覆盖配置
            if persona_data:
                # 获取人设的提示词，去除首尾空格
                prompt = str(persona_data.get("prompt", "")).strip()
                # 如果提示词不为空，使用人设提示词作为指令
                if prompt:
                    instructions = prompt
                # 深拷贝处理后的对话开始数据，避免原始数据被修改
                begin_dialogs = copy.deepcopy(
                    persona_data.get("_begin_dialogs_processed")
                )
                # 获取人设的工具配置
                tools = persona_data.get("tools")
                # 如果公开描述为空且人设提示词存在，使用提示词的前120个字符作为描述
                if public_description == "" and prompt:
                    public_description = prompt[:120]
            
            # 工具配置规范化处理
            if tools is None:
                # 如果工具为 None，保持 None
                tools = None
            elif not isinstance(tools, list):
                # 如果工具不是列表类型，设为空列表
                tools = []
            else:
                # 过滤工具列表：转换为字符串，去除空格，并过滤空字符串
                tools = [str(t).strip() for t in tools if str(t).strip()]

            # 创建 Agent 实例，指定上下文类型为 AstrAgentContext
            agent = Agent[AstrAgentContext](
                name=name,                    # 代理名称
                instructions=instructions,    # 代理指令/系统提示词
                tools=tools,  # type: ignore  # 代理可用的工具列表
            )
            # 设置代理的对话开始数据
            agent.begin_dialogs = begin_dialogs
            
            # 创建移交工具
            # 工具描述是对主 LLM 的简短描述，子代理的系统提示词可以更长更具体
            handoff = HandoffTool(
                agent=agent,                                    # 关联的代理实例
                tool_description=public_description or None,    # 工具描述（优先使用公开描述）
            )

            # 可选的子代理聊天提供商覆盖设置
            handoff.provider_id = provider_id

            # 将创建的移交工具添加到列表中
            handoffs.append(handoff)

        # 记录所有已注册的子代理移交工具
        for handoff in handoffs:
            logger.info(f"Registered subagent handoff tool: {handoff.name}")

        # 更新实例的移交工具列表为本次加载的结果
        self.handoffs = handoffs