# 接入外部知识库

知识库 Backend API 允许插件把远端服务、已有数据库或其他检索系统接入 AstrBot。接入后，Agent 可以通过与内置知识库相同的检索链路使用外部知识。

该接口只标准化知识库发现和只读检索，不负责创建知识库、上传文档、管理分块、配置凭证或备份数据。这些管理能力仍由插件或外部知识库系统负责。

## 实现 Backend

插件需要继承 `BaseKnowledgeBaseBackend` 并实现以下成员：

| 成员 | 用途 |
| --- | --- |
| `backend_id` | Backend 的全局唯一标识。长度为 1–128，只能包含 ASCII 字母、数字、`-`、`_`、`.` 和 `:` |
| `display_name` | 用于日志和错误信息的可读名称 |
| `list_knowledge_bases()` | 返回当前会话已启用且有权访问的知识库 |
| `retrieve()` | 从指定知识库中检索并返回标准结果 |

下面是一个完整的插件结构示例。远端接口的路径和响应字段仅用于演示，请根据实际服务调整。

```python
from typing import Any

import httpx

from astrbot.api import (
    BaseKnowledgeBaseBackend,
    KnowledgeBaseHit,
    KnowledgeBaseInfo,
    KnowledgeBaseQuery,
    KnowledgeBaseRef,
    KnowledgeBaseResponse,
)
from astrbot.api.star import Context, Star


class RemoteKnowledgeBaseBackend(BaseKnowledgeBaseBackend):
    """Expose a remote retrieval service to AstrBot."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        """Initialize the remote backend.

        Args:
            client: Configured client for the remote knowledge base service.
        """
        self.client = client

    @property
    def backend_id(self) -> str:
        """Return the globally unique backend identifier."""
        return "example:remote"

    @property
    def display_name(self) -> str:
        """Return the human-readable backend name."""
        return "Example Remote Knowledge Base"

    async def list_knowledge_bases(
        self,
        *,
        umo: str | None = None,
    ) -> list[KnowledgeBaseInfo]:
        """List enabled knowledge bases visible to the current session.

        Args:
            umo: Unified message origin used for access filtering.

        Returns:
            Enabled knowledge bases that the current session may query.
        """
        response = await self.client.get(
            "/knowledge-bases",
            params={"umo": umo} if umo else None,
        )
        response.raise_for_status()
        return [
            KnowledgeBaseInfo(
                ref=KnowledgeBaseRef(self.backend_id, item["id"]),
                name=item["name"],
                description=item.get("description"),
                metadata=item.get("metadata", {}),
            )
            for item in response.json()["items"]
        ]

    async def retrieve(
        self,
        knowledge_base_ids: list[str],
        request: KnowledgeBaseQuery,
    ) -> KnowledgeBaseResponse:
        """Retrieve relevant content from selected knowledge bases.

        Args:
            knowledge_base_ids: Backend-local knowledge base identifiers.
            request: Standardized retrieval request.

        Returns:
            Ranked retrieval results and non-fatal warnings.
        """
        payload: dict[str, Any] = {
            "knowledge_base_ids": knowledge_base_ids,
            "query": request.query,
            "top_k": request.top_k,
            "umo": request.umo,
        }
        if request.score_threshold is not None:
            payload["score_threshold"] = request.score_threshold
        if request.filters:
            payload["filters"] = request.filters

        response = await self.client.post("/retrieve", json=payload)
        response.raise_for_status()
        data = response.json()
        return KnowledgeBaseResponse(
            hits=[
                KnowledgeBaseHit(
                    ref=KnowledgeBaseRef(
                        self.backend_id,
                        item["knowledge_base_id"],
                    ),
                    content=item["content"],
                    source=item.get("source", self.display_name),
                    rank=index,
                    score=item.get("score"),
                    document_id=item.get("document_id"),
                    chunk_id=item.get("chunk_id"),
                    source_uri=item.get("source_uri"),
                    metadata=item.get("metadata", {}),
                )
                for index, item in enumerate(data["hits"], start=1)
            ],
            warnings=data.get("warnings", []),
        )


class Main(Star):
    """Register the remote knowledge base backend."""

    def __init__(self, context: Context) -> None:
        """Initialize the plugin.

        Args:
            context: AstrBot plugin context.
        """
        super().__init__(context)
        self.client = httpx.AsyncClient(
            base_url="https://knowledge.example.com/api",
            timeout=10,
        )
        self.backend = RemoteKnowledgeBaseBackend(self.client)

    async def initialize(self) -> None:
        """Register the backend when the plugin starts."""
        self.context.register_knowledge_base_backend(self.backend)

    async def terminate(self) -> None:
        """Unregister the backend before releasing its resources."""
        self.context.unregister_knowledge_base_backend(self.backend.backend_id)
        await self.client.aclose()
```

插件拥有 Backend 及其网络连接、线程和其他资源。插件停用或热重载时，AstrBot 会调用 `terminate()`，插件必须先注销 Backend，再关闭它使用的资源。对同一个 `backend_id` 重复注销是安全的。

## 查询语义

`KnowledgeBaseQuery` 包含以下字段：

| 字段 | 语义 |
| --- | --- |
| `query` | 用户查询文本 |
| `top_k` | 整个检索请求最终保留的最大结果数 |
| `score_threshold` | 可选的 Backend 本地相关度阈值 |
| `filters` | 可选的 Backend 专用元数据过滤条件 |
| `umo` | 当前会话的 unified message origin，可用于权限和租户过滤 |

`score_threshold` 和 `filters` 是可选提示。Backend 无法支持时可以忽略，但插件应当在自己的文档中说明。AstrBot 的默认 Agent 检索目前只传递 `query`、`top_k` 和 `umo`。

每个 `KnowledgeBaseHit` 必须携带一个 `ref`，并且该引用必须属于当前 Backend 和本次请求选中的知识库，否则 AstrBot 会丢弃该结果。`rank` 从 1 开始，数值越小表示 Backend 内排名越高。

不同 Backend 的 `score` 不一定处于相同量纲，因此 AstrBot 不按分数直接比较不同 Backend 的结果。多 Backend 结果按各自的 `rank` 合并，再截取全局 `top_k`。`metadata` 只应用于 Backend 专用的附加信息，跨 Backend 使用的身份、来源和排名应填写标准字段。

## 知识库发现和权限

当存在外部 Backend 时，Agent 在检索前会调用每个 Backend 的 `list_knowledge_bases(umo=...)`，然后查询它返回的所有知识库。该方法返回的是“暴露给 AstrBot 自动检索”的集合，而不是远端服务中全部可发现的数据集。因此：

- `list_knowledge_bases()` 只能返回当前 `umo` 有权访问且已经启用的知识库。
- 如果插件需要展示其他可发现但尚未启用的知识库，应通过自己的配置页或 Plugin Pages 提供，不要把它们加入此方法的返回值。
- 如果某个会话不应使用此 Backend，应返回空列表。
- 不要把未经授权的知识库暴露后再依赖 `retrieve()` 二次过滤。
- 列表和检索调用可能并发发生，Backend 实现应避免共享可变的请求状态。

## 错误处理

Backend 可以抛出 `KnowledgeBaseAuthenticationError`、`KnowledgeBaseRateLimitError`、`KnowledgeBaseNotFoundError`、`KnowledgeBaseTimeoutError` 或通用的 `KnowledgeBaseBackendError`。多 Backend 检索会隔离单个 Backend 的异常，将其记录为警告，并继续使用其他可用结果。

能够返回部分结果时，应使用 `KnowledgeBaseResponse.warnings` 描述非致命问题，而不是丢弃已经获得的结果。Backend 返回类型错误、空内容、无效排名或不匹配的知识库引用时，对应结果会被忽略。

## 当前边界

该接口有意保持最小化，只负责：

- 注册和注销 Backend
- 发现当前会话可用的知识库
- 标准化只读检索请求和结果
- 多 Backend 并行调用、故障隔离和结果合并
- 把外部检索结果注入 Agent 上下文

知识库创建、文档上传与删除、分块管理、索引构建、统计、备份、凭证配置和 WebUI 管理不属于该接口。插件可以自行提供命令、配置页或插件 Pages 管理这些能力。
