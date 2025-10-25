import abc
from dataclasses import dataclass


@dataclass
class Result:
    similarity: float
    data: dict


class BaseVecDB:
    async def initialize(self):
        """
        初始化向量数据库
        """
        pass

    @abc.abstractmethod
    async def insert(
        self, content: str, metadata: dict | None = None, id: str | None = None
    ) -> int:
        """
        插入一条文本和其对应向量，自动生成 ID 并保持一致性。
        """
        ...

    @abc.abstractmethod
    async def insert_batch(
        self,
        contents: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
        batch_size: int = 32,
        tasks_limit: int = 3,
        max_retries: int = 3,
        progress_callback=None,
    ) -> int:
        """
        批量插入文本和其对应向量，自动生成 ID 并保持一致性。

        Args:
            progress_callback: 进度回调函数，接收参数 (current, total)
        """
        ...

    @abc.abstractmethod
    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        fetch_k: int = 20,
        rerank: bool = False,
        metadata_filters: dict | None = None,
    ) -> list[Result]:
        """
        搜索最相似的文档。
        Args:
            query (str): 查询文本
            top_k (int): 返回的最相似文档的数量
        Returns:
            List[Result]: 查询结果
        """
        ...

    @abc.abstractmethod
    async def delete(self, doc_id: str) -> bool:
        """
        删除指定文档。
        Args:
            doc_id (str): 要删除的文档 ID
        Returns:
            bool: 删除是否成功
        """
        ...

    @abc.abstractmethod
    async def close(self): ...
