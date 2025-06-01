import aiohttp
import json
from typing import List
from ..provider import EmbeddingProvider
from ..register import register_provider_adapter
from ..entities import ProviderType


@register_provider_adapter(
    "ollama_embedding",
    "Ollama Embedding 提供商适配器",
    provider_type=ProviderType.EMBEDDING,
)
class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)
        self.provider_config = provider_config
        self.provider_settings = provider_settings
        self.base_url = provider_config.get(
            "embedding_api_base", "http://localhost:11434"
        ).rstrip('/')
        self.model = provider_config.get("embedding_model", "nomic-embed-text")
        self.dimension = provider_config.get("embedding_dimensions", 768)
        
        # Ollama 需要明确指定 embedding_only 模式
        self.embedding_options = {
            "embedding_only": True,
            "options": provider_config.get("options", {})
        }

    async def _request_embedding(self, text: str) -> List[float]:
        """向 Ollama 发送请求获取嵌入"""
        url = f"{self.base_url}/api/generate"  # 注意使用 /api/generate 端点
        
        payload = {
            "model": self.model,
            "prompt": text,  # Ollama 使用 "prompt" 而非 "input"
            **self.embedding_options
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(
                        f"Ollama 请求失败: {response.status} - {error_text}"
                    )
                
                # Ollama 的流式响应需要特殊处理
                embedding = []
                async for line in response.content:
                    if line:
                        chunk = json.loads(line.decode('utf-8'))
                        if 'embedding' in chunk:
                            embedding = chunk['embedding']
                            break
                
                if not embedding:
                    raise ValueError("从 Ollama 响应中未获取到嵌入向量")
                
                return embedding

    async def get_embedding(self, text: str) -> List[float]:
        """
        获取单个文本的嵌入
        """
        return await self._request_embedding(text)

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        批量获取文本的嵌入
        """
        return [await self._request_embedding(text) for text in texts]

    def get_dim(self) -> int:
        """获取向量的维度"""
        return self.dimension