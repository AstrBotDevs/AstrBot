from typing import List
from openai import AsyncOpenAI


class SimpleOpenAIEmbedding:
    def __init__(
        self,
        model,
        api_key,
        api_base=None,
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=api_base)
        self.model = model

    async def get_embedding(self, text) -> List[float]:
        """
        获取文本的嵌入
        """
        embedding = await self.client.embeddings.create(input=text, model=self.model)
        return embedding.data[0].embedding
