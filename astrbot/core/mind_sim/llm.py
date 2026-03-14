"""MindSim LLM 调用模块

统一的 LLM 调用接口，支持按角色（deep/medium/fast/function/reply）选择模型。
模型配置来自前端 ProviderMetaData 选择，通过 provider_id 匹配 Provider 实例。
同一个 Provider 只缓存一份，统一 token 统计。
"""

from dataclasses import dataclass
from typing import Optional

from astrbot.core import logger
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from astrbot.core.provider.provider import Provider


@dataclass
class ModelConfig:
    """单个模型配置（对应前端一个模型选择项）"""

    provider_id: str = ""
    """Provider 实例 ID"""
    model: str = ""
    """模型名称"""
    temperature: float = 0.7
    max_tokens: int = 4096


class MindSimLLM:
    """MindSim 统一 LLM 调用

    核心设计：
    - 按角色（deep/medium/fast/function/reply）注册模型配置
    - 通过 provider_id 从 ProviderManager.inst_map 查找 Provider 实例
    - 同一个 provider_id 只缓存一份 Provider 实例
    - 统一 call(role, prompt) 接口，自动路由到对应模型
    - 累计 token 统计
    """

    def __init__(self, provider_manager, default_provider: Provider):
        """
        Args:
            provider_manager: ProviderManager 或具有 inst_map 属性的对象
            default_provider: 默认 Provider（角色未配置时回退使用）
        """
        self._provider_manager = provider_manager
        self._default_provider = default_provider
        # 角色 -> 模型配置
        self._role_configs: dict[str, ModelConfig] = {}
        # provider_id -> Provider 实例缓存
        self._provider_cache: dict[str, Provider] = {}
        # 累计 token 用量
        self._total_usage = TokenUsage()

    def register_model(self, role: str, config: ModelConfig) -> Optional[str]:
        """注册角色对应的模型配置

        从 provider_manager.inst_map 中查找 Provider 实例并缓存。

        Args:
            role: 角色名 (deep/medium/fast/function/reply)
            config: 模型配置

        Returns:
            错误信息字符串，None 表示成功
        """
        if not config.provider_id or not config.model:
            return None  # 空配置，使用默认 provider

        # 查缓存
        provider = self._provider_cache.get(config.provider_id)
        if not provider:
            provider = self._provider_manager.inst_map.get(config.provider_id)
            if not provider:
                return f"提供商 '{config.provider_id}' 不存在或已被删除，请在高级人格设置中重新选择模型"
            self._provider_cache[config.provider_id] = provider

        self._role_configs[role] = config
        logger.info(
            f"[MindSimLLM] 注册模型 role={role}, "
            f"provider={config.provider_id}, model={config.model}"
        )
        return None

    def _get_provider_and_model(self, role: str) -> tuple[Provider, str | None]:
        """获取角色对应的 Provider 实例和模型名

        Returns:
            (Provider 实例, 模型名)。未配置时返回 (默认 Provider, None)
        """
        config = self._role_configs.get(role)
        if not config:
            return self._default_provider, None
        provider = self._provider_cache.get(
            config.provider_id, self._default_provider
        )
        return provider, config.model

    async def call(
        self,
        prompt: str,
        role: str = "deep",
        system_prompt: str = "",
        contexts: list[dict] | None = None,
        temperature: float | None = None,
    ) -> str:
        """统一 LLM 调用接口

        Args:
            prompt: 用户提示词
            role: 模型角色 (deep/medium/fast/function/reply)
            system_prompt: 系统提示词
            contexts: 上下文消息列表（OpenAI 格式）
            temperature: 温度覆盖，None 则使用配置值

        Returns:
            LLM 响应文本

        Raises:
            RuntimeError: LLM 返回错误
            Exception: 调用异常
        """
        provider, model = self._get_provider_and_model(role)
        config = self._role_configs.get(role, ModelConfig())

        # 构建消息列表
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if contexts:
            messages.extend(contexts)
        messages.append({"role": "user", "content": prompt})

        temp = temperature if temperature is not None else config.temperature

        try:
            response: LLMResponse = await provider.text_chat(
                prompt=prompt,
                contexts=messages,
                model=model,
                temperature=temp,
            )

            # 累计 token
            if response.usage:
                self._total_usage = self._total_usage + response.usage

            if response.role == "err":
                raise RuntimeError(
                    f"LLM 返回错误: {response.completion_text or '未知错误'}"
                )

            return response.completion_text or response.reasoning_content or ""

        except Exception as e:
            logger.error(
                f"[MindSimLLM] 调用失败 "
                f"(role={role}, provider={config.provider_id}, model={model}): {e}"
            )
            raise

    async def call_json(
        self,
        prompt: str,
        role: str = "deep",
        system_prompt: str = "",
        contexts: list[dict] | None = None,
    ) -> dict:
        """调用 LLM 并解析 JSON 响应

        Args:
            prompt: 提示词（会自动追加 JSON 输出要求）
            role: 模型角色
            system_prompt: 系统提示词
            contexts: 上下文

        Returns:
            解析后的字典，解析失败返回空字典
        """
        import json
        import re

        response = await self.call(
            prompt=f"{prompt}\n\n请以 JSON 格式输出。",
            role=role,
            system_prompt=system_prompt,
            contexts=contexts,
        )

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            logger.error("[MindSimLLM] JSON 解析失败")
            return {}

    @property
    def token_usage(self) -> TokenUsage:
        """累计 token 用量"""
        return self._total_usage

    @classmethod
    def from_persona_config(
        cls,
        provider: Provider,
        persona_config: dict,
        provider_manager,
    ) -> "MindSimLLM":
        """从高级人格配置创建 MindSimLLM 实例

        Args:
            provider: 默认 Provider 实例
            persona_config: 人格配置字典
            provider_manager: ProviderManager（需要有 inst_map 属性）

        Returns:
            MindSimLLM 实例
        """
        llm = cls(provider_manager=provider_manager, default_provider=provider)

        robot_config = persona_config.get("robot_config", {})
        llm_model_config = robot_config.get("llm_model_config", {})

        # 角色 -> 配置字典的映射
        thinking_models = llm_model_config.get("thinking_models", {})
        role_map = {
            "deep": thinking_models.get("deep", {}),
            "medium": thinking_models.get("medium", {}),
            "fast": thinking_models.get("fast", {}),
            "function": llm_model_config.get("function_model", {}),
            "reply": llm_model_config.get("reply_model", {}),
        }

        errors = []
        for role, cfg_dict in role_map.items():
            if not cfg_dict:
                continue
            config = ModelConfig(
                provider_id=cfg_dict.get("provider_id", ""),
                model=cfg_dict.get("model", ""),
                temperature=cfg_dict.get("temperature", 0.7),
                max_tokens=cfg_dict.get("max_tokens", 4096),
            )
            error = llm.register_model(role, config)
            if error:
                errors.append(f"{role}: {error}")
                logger.warning(f"[MindSimLLM] {role} 模型注册失败: {error}")

        if errors:
            logger.warning(
                f"[MindSimLLM] 部分模型注册失败，将使用默认 Provider 回退: "
                + "; ".join(errors)
            )

        return llm
