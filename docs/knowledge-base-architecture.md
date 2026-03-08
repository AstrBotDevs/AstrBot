# 知识库底层架构设计说明

> 对应 Issue: #5262
> 分支: `rag-enhancement`
> 最后更新: 2026-03-08

---

## 1. 概述

本次重构在原有知识库系统的基础上引入两个核心能力：

1. **Provider 隔离的 FAISS 索引** — 支持 Embedding 模型热切换，无需全量重建即可在不同模型间切换
2. **结构化文档索引** — 支持按 Markdown 标题层级建立章节索引，由 LLM 按需读取正文

整体目标是让知识库系统更灵活、可扩展，同时保持与旧版本的向后兼容。

---

## 2. 系统架构总览

```
┌─────────────────────────────────────────────────────────┐
│                     Dashboard / API                      │
│  /kb/create  /kb/update  /kb/rebuild/progress  ...      │
└───────────────────────────┬─────────────────────────────┘
                            │
                ┌───────────▼───────────┐
                │  KnowledgeBaseManager  │
                │      (kb_mgr.py)       │
                │                        │
                │  - kb_insts: dict      │
                │  - rebuild_tasks       │
                │  - index_rebuilder     │
                └───────┬───────────────┘
                        │
          ┌─────────────▼──────────────┐
          │         KBHelper            │
          │       (kb_helper.py)        │
          │                             │
          │  - kb: KnowledgeBase        │
          │  - vec_db: FaissVecDB       │
          │  - kb_db: KBSQLiteDatabase  │
          │  - chunker                  │
          └──────┬──────────────┬───────┘
                 │              │
    ┌────────────▼───┐   ┌─────▼──────────────┐
    │   FaissVecDB   │   │  KBSQLiteDatabase   │
    │  (vec_db.py)   │   │ (kb_db_sqlite.py)   │
    │                │   │                      │
    │ ┌────────────┐ │   │  knowledge_bases     │
    │ │ Document   │ │   │  kb_documents        │
    │ │ Storage    │ │   │  kb_media            │
    │ │ (doc.db)   │ │   │  doc_sections (NEW)  │
    │ └────────────┘ │   └──────────────────────┘
    │ ┌────────────┐ │
    │ │ Embedding  │ │
    │ │ Storage    │ │
    │ │ (.faiss)   │ │
    │ └────────────┘ │
    └────────────────┘
```

### 关键数据流

```
用户上传文档
    │
    ├── flat 模式 ──→ 解析 → 分块(Chunker) → Embedding → FAISS + doc.db
    │
    └── structure 模式 ──→ 解析 → StructureParser → 章节 path Embedding → FAISS + doc.db + doc_sections
```

```
用户检索
    │
    ├── Dense 检索 (FAISS 向量相似度)
    ├── Sparse 检索 (BM25)
    ├── RRF 融合
    ├── Rerank (可选)
    │
    ├── flat 结果 ──→ 直接返回 chunk 正文
    └── structure 结果 ──→ 返回章节路径标记 → LLM 调用 ReadDocumentSectionTool 获取正文
```

---

## 3. 数据模型

### 3.1 元数据库 (kb.db)

位于 `data/knowledge_base/kb.db`，使用 SQLite + SQLAlchemy async，存储所有知识库的元数据。

#### knowledge_bases 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| kb_id | VARCHAR(36) UNIQUE | 知识库唯一标识 |
| kb_name | VARCHAR(100) UNIQUE | 知识库名称 |
| description | TEXT | 描述 |
| emoji | VARCHAR(10) | 图标 |
| embedding_provider_id | VARCHAR(100) | **期望**使用的 Embedding Provider |
| **active_index_provider_id** | VARCHAR(100) | **实际**生效的索引 Provider (NEW) |
| **default_index_mode** | VARCHAR(20) | 默认索引模式: `flat` / `structure` (NEW) |
| rerank_provider_id | VARCHAR(100) | Rerank Provider |
| chunk_size | INTEGER | 分块大小 |
| chunk_overlap | INTEGER | 分块重叠 |
| top_k_dense | INTEGER | 稠密检索数量 |
| top_k_sparse | INTEGER | 稀疏检索数量 |
| top_m_final | INTEGER | 最终返回数量 |
| doc_count | INTEGER | 文档计数 |
| chunk_count | INTEGER | 块计数 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

**`embedding_provider_id` 与 `active_index_provider_id` 的区别：**

- `embedding_provider_id`：用户在 Dashboard 上配置的"期望"使用的模型
- `active_index_provider_id`：当前 FAISS 索引实际对应的模型

当两者不一致时，系统会自动触发后台索引重建。重建完成后两者同步。

#### kb_documents 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| doc_id | VARCHAR(36) UNIQUE | 文档唯一标识 |
| kb_id | VARCHAR(36) | 所属知识库 |
| doc_name | VARCHAR(255) | 文档名称 |
| file_type | VARCHAR(20) | 文件类型 |
| file_size | INTEGER | 文件大小 |
| file_path | VARCHAR(512) | 文件路径 |
| **index_mode** | VARCHAR(20) | 索引模式: `flat` / `structure` (NEW) |
| chunk_count | INTEGER | 块数量 |
| media_count | INTEGER | 媒体数量 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

#### doc_sections 表 (NEW)

存储结构化文档的章节信息，供 LLM 按需读取正文。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| section_id | VARCHAR(36) UNIQUE | 章节唯一标识 |
| doc_id | VARCHAR(36) | 所属文档 |
| kb_id | VARCHAR(36) | 所属知识库 |
| section_path | VARCHAR(1024) | 章节路径，如 `"第一章/API 设计"` |
| section_level | INTEGER | 标题层级 (1-6) |
| section_title | VARCHAR(255) | 章节标题 |
| section_body | TEXT | 章节正文内容 |
| parent_section_id | VARCHAR(36) | 父章节 ID |
| sort_order | INTEGER | 排序序号 |

### 3.2 向量文档库 (doc.db)

每个知识库独立一份，位于 `data/knowledge_base/{kb_id}/doc.db`。

#### documents 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键，同时作为 FAISS 的 int ID |
| doc_id | VARCHAR | chunk UUID |
| text | TEXT | chunk 文本内容 |
| metadata | TEXT (JSON) | 元数据 JSON |
| is_indexed | BOOLEAN | 索引状态标记 (NEW) |
| source_hash | TEXT | 内容 SHA256 哈希 (NEW) |
| kb_doc_id | GENERATED | 从 metadata JSON 提取 |
| user_id | GENERATED | 从 metadata JSON 提取 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### 3.3 FAISS 索引文件

```
data/knowledge_base/{kb_id}/
├── doc.db                                    # 向量文档数据库
├── index.{provider_id}.faiss                 # Provider 隔离的 FAISS 索引 (NEW)
├── medias/{kb_id}/                           # 媒体文件
└── files/{kb_id}/                            # 原始文件
```

**旧版命名**：`index.faiss`
**新版命名**：`index.{normalized_provider_id}.faiss`

provider_id 通过 `normalize_provider_id()` 处理，将文件系统不安全字符替换为 `_`。

---

## 4. 功能一：Provider 隔离索引与热切换

### 4.1 设计目标

用户在 Dashboard 上切换 Embedding 模型时，系统应：

1. 不阻塞当前服务 — 旧索引继续可用
2. 后台增量重建新索引
3. 重建完成后原子切换到新索引
4. 支持进度查询

### 4.2 索引路径规则

```python
# index_path.py

def normalize_provider_id(provider_id: str) -> str:
    """将 provider_id 中的非安全字符替换为下划线"""
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", provider_id)

def build_index_path(kb_dir: Path, provider_id: str) -> Path:
    return kb_dir / f"index.{normalize_provider_id(provider_id)}.faiss"
```

示例：
- provider_id = `openai/text-embedding-3-small` → 文件名 `index.openai_text-embedding-3-small.faiss`
- provider_id = `local-bge-m3` → 文件名 `index.local-bge-m3.faiss`

### 4.3 索引加载流程

```
KBHelper.initialize()
    │
    ├── active_index_provider_id 为空？
    │   └── 是 → 设为 embedding_provider_id，持久化
    │
    └── _ensure_vec_db()
            │
            └── get_active_index_path()
                    │
                    └── build_index_path(kb_dir, active_provider_id)
                            │
                            └── FaissVecDB(index_store_path=...)
```

### 4.4 索引重建流程

触发条件：`embedding_provider_id != active_index_provider_id`

```
KnowledgeBaseManager.start_rebuild_index(kb_id, new_provider_id)
    │
    ├── 检查是否已有正在进行的重建任务
    │
    ├── 创建 task_id，记录到 rebuild_tasks
    │
    └── asyncio.create_task(_run())
            │
            └── IndexRebuilder.sync()
                    │
                    ├── 1. 获取新 Provider 实例
                    ├── 2. 创建新的 EmbeddingStorage（新路径）
                    ├── 3. 计算增量 diff：
                    │       doc_int_ids = doc.db 中所有 ID
                    │       index_int_ids = 新 FAISS 中已有 ID
                    │       to_delete = index_int_ids - doc_int_ids
                    │       to_add = doc_int_ids - index_int_ids
                    ├── 4. 批量删除 to_delete
                    ├── 5. 批量 embedding + 插入 to_add
                    ├── 6. 更新 active_index_provider_id → persist_kb()
                    └── 7. switch_index() 切换内存中的 FAISS 实例
```

### 4.5 进度查询

Dashboard 可通过 `GET /kb/rebuild/progress?kb_id=xxx` 轮询重建进度：

```json
{
  "task_id": "uuid",
  "kb_id": "uuid",
  "provider_id": "new-provider-id",
  "status": "processing",   // processing | completed | failed
  "stage": "embedding",     // prepare | deleting | embedding | finished
  "current": 150,
  "total": 500,
  "error": null
}
```

### 4.6 switch_index 热切换

```python
# vec_db.py
async def switch_index(self, index_store_path, embedding_provider, rerank_provider=None):
    self.index_store_path = index_store_path
    self.embedding_provider = embedding_provider
    self.rerank_provider = rerank_provider
    self.embedding_storage = EmbeddingStorage(
        embedding_provider.get_dim(),
        index_store_path,
    )
```

切换后，新的检索请求会使用新的 Provider 和新的 FAISS 索引，旧索引文件保留在磁盘上不删除。

---

## 5. 功能二：结构化文档索引

### 5.1 设计目标

对于有清晰标题层级的文档（如 Markdown），不做全文分块，而是按标题结构建立章节索引。检索时只返回匹配的章节路径，由 LLM 决定是否调用工具读取完整正文。

**优势**：
- 避免将长文档切成碎片导致上下文丢失
- LLM 可以按需获取完整章节，保持内容完整性
- 减少无关内容的 token 消耗

### 5.2 结构解析

`StructureParser` 解析 Markdown 标题层级：

```python
# structure_parser.py

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
```

输入：
```markdown
# 第一章
正文内容...
## API 设计
API 设计正文...
## 数据模型
数据模型正文...
# 第二章
```

输出（SectionNode 树）：
```
SectionNode(title="第一章", level=1, path="第一章", body="正文内容...")
├── SectionNode(title="API 设计", level=2, path="第一章/API 设计", body="API 设计正文...")
└── SectionNode(title="数据模型", level=2, path="第一章/数据模型", body="数据模型正文...")
SectionNode(title="第二章", level=1, path="第二章", body="")
```

`flatten()` 将树形结构展平为列表，保留 path 字段作为唯一标识。

支持的文件类型：`md`、`markdown`、`txt`。其他类型返回空列表，自动 fallback 到 flat 模式。

### 5.3 结构化上传流程

```
kb_helper._upload_document_structured()
    │
    ├── 1. 解析文档 → parse_result.text
    ├── 2. StructureParser.parse_structure() → SectionNode 树
    ├── 3. flatten() → 章节列表
    │
    ├── 4. 如果章节列表为空 → fallback 到 flat 模式
    │
    ├── 5. 向量化：contents = [section.path for section in sections]
    │       （当前嵌入的是章节路径字符串）
    │
    ├── 6. 插入 doc.db：documents 表（text = section.path, metadata 含 index_mode/section_path）
    ├── 7. 插入 FAISS：embedding_storage.insert_batch()
    │
    ├── 8. 插入 kb.db：
    │       ├── kb_documents 表（index_mode = "structure"）
    │       └── doc_sections 表（每个章节一条记录，存储完整 body）
    │
    └── 9. 更新统计
```

### 5.4 结构化检索流程

检索结果中，结构化文档的 chunk metadata 包含 `index_mode: "structure"` 和 `section_path`。

**上下文格式化**（`kb_mgr._format_context`）：

```python
if index_mode == "structure" and section_path:
    # 不直接返回正文，而是返回章节路径标记
    lines.append(f"内容: [📖 {section_path}]")
    lines.append(
        f"提示: 如需正文，请调用 astr_kb_read_section("
        f"doc_id='{result.doc_id}', section_path='{section_path}')"
    )
```

### 5.5 ReadDocumentSectionTool

LLM 可用的工具，按 doc_id + section_path 从 `doc_sections` 表读取完整正文：

```python
@dataclass
class ReadDocumentSectionTool(FunctionTool[AstrAgentContext]):
    name: str = "astr_kb_read_section"
    # parameters: doc_id, section_path
```

调用链：
```
LLM 调用 astr_kb_read_section(doc_id, section_path)
    → read_knowledge_base_section()
        → kb_mgr.read_document_section(kb_names, doc_id, section_path)
            → kb_db.get_doc_section(kb_id, doc_id, section_path)
                → 精确匹配 section_path
                → 如失败，LIKE 模糊匹配
```

该工具仅在知识库中存在结构化文档时注册（`has_structured_docs_by_names()`）。

---

## 6. 数据库迁移

### 6.1 迁移链路

```
启动 → initialize() → create_all (建表) → migrate_to_v1 → migrate_to_v2 → migrate_to_v3
```

每次迁移都是幂等的，通过 `try/except` 在 `ALTER TABLE ADD COLUMN` 时捕获"列已存在"异常。

### 6.2 migrate_to_v1

创建查询优化索引（`CREATE INDEX IF NOT EXISTS`），纯幂等操作。

### 6.3 migrate_to_v2

**变更内容**：
1. `knowledge_bases` 表添加 `active_index_provider_id` 列
2. 遍历所有知识库，回填 `active_index_provider_id = embedding_provider_id`
3. 重命名 FAISS 索引文件：`index.faiss` → `index.{provider_id}.faiss`

**文件重命名逻辑**：
```python
old_index_path = kb_root / kb.kb_id / "index.faiss"
new_index_path = build_index_path(kb_root / kb.kb_id, kb.embedding_provider_id)
if old_index_path.exists() and not new_index_path.exists():
    old_index_path.rename(new_index_path)
```

**安全性**：
- 只在旧文件存在且新文件不存在时重命名，幂等
- 重命名是原子操作（同一文件系统内）
- 不删除任何数据，只是文件改名

### 6.4 migrate_to_v3

**变更内容**：
1. `knowledge_bases` 表添加 `default_index_mode` 列（默认 `'flat'`）
2. `kb_documents` 表添加 `index_mode` 列（默认 `'flat'`）
3. 回填所有 NULL 值为 `'flat'`

纯 schema 变更 + 数据回填，不涉及文件操作。

### 6.5 DocumentStorage 迁移

**变更内容**：
1. `documents` 表添加 `is_indexed` 列
2. `documents` 表添加 `source_hash` 列
3. 回填 `is_indexed = 1`

### 6.6 向后兼容

- 所有迁移只做 **ADD COLUMN**，不 DROP / ALTER 现有列
- `create_all` 只创建不存在的表，不修改已有表
- 旧数据完全保留，新列以合理默认值填充
- 旧版 FAISS 文件被重命名而非删除

---

## 7. 文件目录结构

```
data/knowledge_base/
├── kb.db                                          # 元数据库（所有知识库共用）
│
├── {kb_id_1}/
│   ├── doc.db                                     # 向量文档库
│   ├── index.openai_text-embedding-3-small.faiss  # Provider A 的索引
│   ├── index.local-bge-m3.faiss                   # Provider B 的索引（切换后保留）
│   ├── medias/{kb_id_1}/                          # 文档中提取的媒体
│   └── files/{kb_id_1}/                           # 原始上传文件
│
├── {kb_id_2}/
│   ├── doc.db
│   ├── index.{provider_id}.faiss
│   └── ...
```

多个 `.faiss` 文件可以共存，只有 `active_index_provider_id` 对应的那个会被加载。

---

## 8. 检索管线

```
           查询文本
              │
    ┌─────────┼─────────┐
    ▼                    ▼
Dense 检索           Sparse 检索
(FAISS L2)            (BM25)
    │                    │
    ▼                    ▼
 向量结果            稀疏结果
    │                    │
    └─────────┬──────────┘
              ▼
      RRF 融合排序
        (top_k)
              │
              ▼
     Rerank (可选)
   (Cohere/BGE-reranker)
              │
              ▼
       top_m 最终结果
              │
    ┌─────────┴─────────┐
    ▼                    ▼
 flat chunk         structure marker
 → 直接返回正文      → 返回章节路径
                     → LLM 按需调用
                       ReadDocumentSectionTool
```

### 检索参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| top_k_dense | Dense 检索返回数量 | 50 |
| top_k_sparse | Sparse 检索返回数量 | 50 |
| top_k_fusion | RRF 融合后保留数量 | 20 |
| top_m_final | 最终返回给 LLM 的数量 | 5 |

---

## 9. API 接口

### 新增接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/kb/rebuild/progress` | 查询索引重建进度 |

### 变更接口

| 方法 | 路径 | 变更 |
|------|------|------|
| POST | `/kb/create` | 新增 `default_index_mode` 参数 |
| POST | `/kb/update` | 新增 `default_index_mode` 参数；切换 Provider 时返回 `rebuild_task_id` |
| POST | `/kb/document/upload` | 新增 `index_mode` 参数 |

### LLM 工具

| 工具名 | 说明 | 注册条件 |
|--------|------|----------|
| `astr_kb_search` | 知识库检索（已有） | 知识库启用时 |
| `astr_kb_read_section` | 读取结构化章节正文（NEW） | 存在 structure 模式文档时 |

---

## 10. 关键模块说明

### index_path.py

纯工具函数，无状态。负责构建文件系统安全的 FAISS 索引路径。

### index_rebuilder.py

`IndexRebuilder` 类，实现增量同步逻辑。通过比较 doc.db 中的文档 ID 集合和新 FAISS 索引中的 ID 集合，计算 `to_add` 和 `to_delete`，避免全量重建。

### structure_parser.py

`StructureParser` 类，解析 Markdown 标题层级为 `SectionNode` 树。`flatten()` 展平为列表，每个节点的 `path` 字段（如 `"第一章/API 设计"`）作为唯一标识。

### kb_helper.py

知识库实例的核心操作类。新增：
- `get_active_index_path()` — 根据 active provider 构建索引路径
- `persist_kb()` — 持久化 KB 元数据变更
- `_upload_document_structured()` — 结构化文档上传

### kb_mgr.py

知识库管理器。新增：
- `start_rebuild_index()` — 启动后台索引重建
- `get_rebuild_progress()` — 查询重建进度
- `has_structured_docs_by_names()` — 检查是否有结构化文档
- `read_document_section()` — 读取章节正文
- 启动时自检：Provider 不一致则自动触发重建

---

## 11. 备份与恢复

### 导出

- 使用 glob 模式 `index*.faiss` 匹配所有 Provider 的索引文件
- `doc_sections` 表包含在 `KB_METADATA_MODELS` 中，随知识库元数据一起导出
- `schema_version.kb_db` 标记为 `v3`

### 导入

- 兼容旧版单文件 `index.faiss` 和新版多文件 `index.{provider}.faiss`
- 导入后调用 `load_kbs()` 重新初始化所有知识库实例
- 如果导入的备份来自旧版本，`migrate_to_v2/v3` 会在 `_init_kb_database` 中自动执行
