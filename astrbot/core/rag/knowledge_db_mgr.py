import os
from typing import List, Dict
from astrbot.core import logger
from .store import Store
from astrbot.core.config import AstrBotConfig


class KnowledgeDBManager:
    def __init__(self, astrbot_config: AstrBotConfig) -> None:
        self.db_path = "data/knowledge_db/"
        self.config = astrbot_config.get("knowledge_db", {})
        self.astrbot_config = astrbot_config
        if not os.path.exists(self.db_path):
            os.makedirs(self.db_path)
        self.store_insts: Dict[str, Store] = {}
        for name, cfg in self.config.items():
            if cfg["strategy"] == "embedding":
                logger.info(f"加载 Chroma Vector Store：{name}")
                try:
                    from .store.chroma_db import ChromaVectorStore
                except ImportError as ie:
                    logger.error(f"{ie} 可能未安装 chromadb 库。")
                    continue
                self.store_insts[name] = ChromaVectorStore(
                    name, cfg["embedding_config"]
                )
            else:
                logger.error(f"不支持的策略：{cfg['strategy']}")

    async def list_knowledge_db(self) -> List[str]:
        return [
            f
            for f in os.listdir(self.db_path)
            if os.path.isfile(os.path.join(self.db_path, f))
        ]

    async def create_knowledge_db(self, name: str, config: Dict):
        """
        config 格式：
        ```
        {
            "strategy": "embedding", # 目前只支持 embedding
            "chunk_method": {
                "strategy": "fixed",
                "chunk_size": 100,
                "overlap_size": 10
            },
            "embedding_config": {
                "strategy": "openai",
                "base_url": "",
                "model": "",
                "api_key": ""
            }
        }
        ```
        """
        if name in self.config:
            raise ValueError(f"知识库已存在：{name}")

        self.config[name] = config
        self.astrbot_config["knowledge_db"] = self.config
        self.astrbot_config.save_config()

    async def insert_record(self, name: str, text: str):
        if name not in self.store_insts:
            raise ValueError(f"未找到知识库：{name}")

        ret = []
        match self.config[name]["chunk_method"]["strategy"]:
            case "fixed":
                chunk_size = self.config[name]["chunk_method"]["chunk_size"]
                chunk_overlap = self.config[name]["chunk_method"]["overlap_size"]
                ret = self._fixed_chunk(text, chunk_size, chunk_overlap)
            case _:
                pass

        for chunk in ret:
            await self.store_insts[name].save(chunk)

    async def retrive_records(self, name: str, query: str, top_n: int = 3) -> List[str]:
        if name not in self.store_insts:
            raise ValueError(f"未找到知识库：{name}")

        inst = self.store_insts[name]
        return await inst.query(query, top_n)

    def _fixed_chunk(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - chunk_overlap
        return chunks
