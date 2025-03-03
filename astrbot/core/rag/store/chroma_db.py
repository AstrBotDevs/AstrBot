import chromadb
import uuid
from typing import List, Dict
from astrbot.api import logger
from ..embedding.openai_source import SimpleOpenAIEmbedding
from . import Store


class ChromaVectorStore(Store):
    def __init__(self, name: str, embedding_cfg: Dict) -> None:
        self.chroma_client = chromadb.PersistentClient(
            path="data/long_term_memory_chroma.db"
        )
        self.collection = self.chroma_client.get_or_create_collection(name=name)
        self.embedding = None
        if embedding_cfg["strategy"] == "openai":
            self.embedding = SimpleOpenAIEmbedding(
                model=embedding_cfg["model"],
                api_key=embedding_cfg["api_key"],
                api_base=embedding_cfg.get("base_url", None),
            )

    async def save(self, text: str, metadata: Dict = None):
        logger.debug(f"Saving text: {text}")
        embedding = await self.embedding.get_embedding(text)

        self.collection.upsert(
            documents=text,
            metadatas=metadata,
            ids=str(uuid.uuid4()),
            embeddings=embedding,
        )

    async def query(
        self, query: str, top_n=3, metadata_filter: Dict = None
    ) -> List[str]:
        embedding = await self.embedding.get_embedding(query)

        results = self.collection.query(
            query_embeddings=embedding, n_results=top_n, where=metadata_filter
        )
        return results["documents"][0]
