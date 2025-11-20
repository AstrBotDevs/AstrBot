from datetime import datetime

from pydantic import BaseModel

"""
我们参考艾宾浩斯遗忘曲线，基于这两个变量设计了一个公式，其表示了每个对话总结的遗忘得分。

$decayscore = alpha * exp(-lambda * delta_t * \beta) + (1-alpha) * (1-exp(-gamma * c))$

其中：

- $delta_t$： 自上次检索以来经过的时间（以天为单位）。
- $c$： 检索次数。
- $alpha$： 控制时间衰减和检索次数影响的权重
- $gamma$： 控制检索次数影响的速率
- $lambda$： 控制时间衰减影响的速率
- $beta$： 时间衰减的调节因子

$beta = frac{1}{1 + a * c}$

- $a$： 控制检索次数对时间衰减影响的权重

相似记忆的合并：

对相似记忆我们有两种处理模式：

- 过于相似的记忆，我们会执行合并成新的记忆。
- 较为相似的记忆，比如某些实体相同，根据赫布理论，我们会提升相似记忆的记忆强度和使用频率。

具体算法如下：

1. 计算新记忆与现有记忆的相似度。
2. 根据相似度，执行以下操作：
   - 如果相似度超过高阈值，合并记忆内容
   - 如果相似度在中等范围内
   - 如果不是高似记忆，都按正常流程存储新记忆。
"""


class MemoryChunk(BaseModel):
    """A chunk of memory stored in the system."""

    id: str
    fact: str
    """The factual content of the memory chunk."""
    created_at: datetime
    """The timestamp when the memory chunk was created."""
    last_retrieval_at: datetime
    """The timestamp when the memory chunk was last retrieved."""
    retrieval_count: int
    """The number of times the memory chunk has been retrieved."""
    importance_bias: float
    """A bias score indicating the importance of the memory chunk."""


# from astrbot.core.db.vec_db.faiss_impl import FaissVecDB
# from astrbot.core.provider.provider import EmbeddingProvider

# memdb = None


# async def test_mem(embed_provider: EmbeddingProvider):
#     global memdb
#     mem_doc_path = "data/astr_memory/doc.db"
#     mem_index_path = "data/astr_memory/index.faiss"
#     memdb = FaissVecDB(
#         doc_store_path=mem_doc_path,
#         index_store_path=mem_index_path,
#         embedding_provider=embed_provider,
#     )
#     await memdb.initialize()


# @dataclass
# class AddMemory(FunctionTool[AstrAgentContext]):
#     name: str = "astr_add_memory"
#     description: str = (
#         "Add a new memory to the user's long-term memory storage. "
#         "Use this tool only when the user explicitly asks you to remember something, "
#         "or when they share stable preferences, identity, or long-term goals that will be useful in future interactions."
#     )
#     parameters: dict = Field(
#         default_factory=lambda: {
#             "type": "object",
#             "properties": {
#                 "query": {
#                     "type": "string",
#                     "description": "A concise keyword query for the knowledge base.",
#                 },
#             },
#             "required": ["query"],
#         }
#     )

#     async def call(
#         self, context: ContextWrapper[AstrAgentContext], **kwargs
#     ) -> ToolExecResult:
#         query = kwargs.get("query", "")
#         if not query:
#             return "error: Query parameter is empty."
#         result = await retrieve_knowledge_base(
#             query=kwargs.get("query", ""),
#             umo=context.context.event.unified_msg_origin,
#             context=context.context.context,
#         )
#         if not result:
#             return "No relevant knowledge found."
#         return result
