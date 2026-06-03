from google import genai
from google.genai import types
from google.genai.errors import APIError

from astrbot import logger

from ..entities import ProviderType
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "gemini_embedding",
    "Google Gemini Embedding 提供商适配器",
    provider_type=ProviderType.EMBEDDING,
)
class GeminiEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings

        # 使用 .get() 避免缺少配置时引发 KeyError 崩溃
        api_key: str = provider_config.get("embedding_api_key", "")
        api_base: str = provider_config.get("embedding_api_base", "")
        timeout: int = int(provider_config.get("timeout", 20))

        # GenAI SDK 的 timeout 单位是毫秒
        http_options = types.HttpOptions(timeout=timeout * 1000)
        
        if api_base:
            api_base = api_base.removesuffix("/")
            http_options.base_url = api_base
            
        proxy = provider_config.get("proxy", "")
        if proxy:
            # 确保 proxy 配置包含协议头 (如 http://...)
            http_options.async_client_args = {"proxy": proxy}
            logger.info(f"[Gemini Embedding] 使用代理: {proxy}")

        self.client = genai.Client(api_key=api_key, http_options=http_options).aio

        self.model = provider_config.get(
            "embedding_model",
            "gemini-embedding-exp-03-07",
        )

    async def get_embedding(self, text: str) -> list[float]:
        # 获取文本的嵌入
        if not text or not text.strip():
            raise ValueError("输入文本不能为空")
            
        try:
            result = await self.client.models.embed_content(
                model=self.model,
                contents=text,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.get_dim(),
                ),
            )
            
            # 使用显式检查替代 assert，防止生产环境下 -O 优化跳过 assert 校验
            if not result.embeddings or not result.embeddings[0].values:
                raise ValueError("API 响应异常：未返回有效的 embedding 数据")
                
            return result.embeddings[0].values
        except APIError as e:
            raise Exception(f"Gemini Embedding API请求失败: {e.message}")
        except Exception as e:
            raise Exception(f"Gemini Embedding 发生异常: {str(e)}")

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        # 批量获取文本的嵌入
        if not text:
            return []
            
        try:
            # 构造 Content 列表以规避 gemini-embedding-2 批处理单返回 bug
            contents = [
                types.Content(parts=[types.Part.from_text(text=s)]) for s in text
            ]
            
            result = await self.client.models.embed_content(
                model=self.model,
                contents=contents,
                config=types.EmbedContentConfig(
                    output_dimensionality=self.get_dim(),
                ),
            )
            
            # 校验返回的数量是否和请求数量匹配
            if not result.embeddings or len(result.embeddings) != len(text):
                actual_len = len(result.embeddings) if result.embeddings else 0
                raise ValueError(f"API 响应异常：向量数量不匹配 (期望 {len(text)}, 实际 {actual_len})")

            embeddings: list[list[float]] = []
            for embedding in result.embeddings:
                if not embedding.values:
                    raise ValueError("API 响应异常：返回的部分 embedding 缺失 values")
                embeddings.append(embedding.values)
                
            return embeddings
        except APIError as e:
            raise Exception(f"Gemini Embedding API批量请求失败: {e.message}")
        except Exception as e:
            raise Exception(f"Gemini Embedding 批量请求发生异常: {str(e)}")

    def get_dim(self) -> int:
        # 获取向量的维度
        return int(self.provider_config.get("embedding_dimensions", 768))

    async def terminate(self):
        # 释放资源
        if getattr(self, 'client', None):
            await self.client.aclose()
