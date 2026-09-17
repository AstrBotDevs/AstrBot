## Context

See `proposal.md` and the three delta specs. The current provider request path turns image references into complete data URIs, while conversation saving serializes the model-visible message list. Image preparation currently focuses on longest-edge pixels and can pass through large pixel-compliant files. Existing histories already contain inline data URIs and must remain readable.

## Goals / Non-Goals

**Goals:**

- Establish one preparation boundary shared by all image-producing inputs.
- Bound the encoded payload that can enter a provider request.
- Separate durable conversation records from media bytes and resolve media only for selected active messages.
- Keep old inline histories readable and make migration explicit.
- Measure file size, encoded payload size, request size, RSS high-water mark, Python allocations, temporary files, and post-request retention.

**Non-Goals:**

- Do not silently remove images from the active context merely to improve memory metrics.
- Do not rewrite existing conversations during ordinary reads.
- Do not assume the 5 MiB limit from #10089 applies to every provider.
- Do not make the provider-specific wire format depend on the persistence representation.

## Decisions

### 1. Use a media reference as the persistence boundary

New history image parts use a versioned internal media reference containing a content hash, MIME type, dimensions, encoded byte size, and original image-detail metadata. Durable image objects live in a dedicated media directory under the configured AstrBot data root, NEVER the temporary directory or its age-based cleanup policy. Provider adapters continue to receive their existing image content shape after request-time materialization. No extra image-caption model is introduced.

Alternative rejected: keep base64 in history and only trim it during compaction. This reduces some requests but leaves database growth, repeated JSON parsing, and compaction-record duplication.

### 2. Keep backward-compatible dual readers

The history reader accepts both the new reference form and existing inline `data:`/base64 forms. The writer emits references only for newly prepared images. Conversion of existing records is an explicit repair/migration operation with backup, dry-run statistics, hash verification, and rollback by restoring the original history.

Alternative rejected: automatic in-place migration on first read. It makes a read destructive and risks losing recoverability when the media directory is unavailable.

### 3. Make encoded bytes a first-class limit

Image preparation uses independent limits for maximum dimensions and maximum encoded payload bytes. Compute base64 length as `4 * ceil(encoded_file_bytes / 3)` without allocating a base64 copy for every candidate. Retain only the current best candidate. Preserve already-compliant original bytes; otherwise try the original supported format and JPEG quality steps, select a valid candidate without enlarging compliant source content, and encode base64 only at the provider boundary. Preserve transparency when required. If no candidate fits, return a readable size error rather than silently returning the original oversized image.

Proposed product defaults: preserve existing dimension and quality settings, add `image_compress_options.max_encoded_bytes = 4194304` (4 MiB of base64 per image). This is an AstrBot preparation budget, not a claim about vendor limits. A documented or configured smaller provider limit takes precedence. A known aggregate request limit is checked against the complete serialized request, independently of this per-image budget. Never reinterpret base64 bytes as text tokens. No universal aggregate vendor limit is invented.

For CUA, preserve the oriented original pixel dimensions and coordinates; try encoding changes without resizing and return a readable error if the budget cannot be met. Do not use an enormous pixel limit as a substitute for an explicit preserve-dimensions flag. Animation follows the selected baseline's frame-selection behavior; an older branch that skips animations is not silently treated as the current montage implementation. Do not keep all decoded animation frames resident simultaneously.

Alternative rejected: use only pixel dimensions or only source-file bytes. Neither predicts the final JSON payload reliably.

### 4. Materialize only selected references

Context selection happens before resolving media references. Images not selected for either the main request or a separate image-capable summary request are not opened, decoded, or encoded. The summary request and the subsequent main request have separate measured lifetimes. Selected references are materialized into a request-local structure and released after the request; the history model never receives the resulting data URI. In-flight cancellation must not delete a file still used by a non-cancelled image worker; cleanup runs when that worker actually exits.

For a fixed provider configuration, prepared historical bytes are immutable. Do not re-encode the history when a new image arrives, tune old JPEG quality to the remaining request space, or substitute captions to achieve memory targets. Ordinary summary/truncation semantics are unchanged. A known oversized aggregate request fails clearly; this project does not add image eviction or a new compression trigger. B-only lazy loading MUST send byte-identical image content to the baseline.

Alternative rejected: materialize all references first and let the context manager remove messages afterward. That preserves the current memory spike and defeats lazy loading.

### 5. Treat all sources as adapters to one preparation function

Platform attachments, quoted content, plugin/MCP results, file tools, and CUA screenshots normalize to a common input descriptor. The descriptor carries source ownership and cleanup responsibility. The preparation function owns format detection, dimension checks, byte checks, temporary-file cleanup, and diagnostic metadata.

### 6. Use an external-process ablation harness

Each measurement case runs in a fresh child process. The harness records RSS at high frequency, Python allocation snapshots separately, request JSON size, image byte sizes, media object counts, and temporary files. Cold-start, warm-start, single-image, multi-image, long-history, concurrent, restart, and missing-media cases are separate workloads.

The implementation is accepted only when the optimized path preserves image count/order and provider-visible content for the active window. Memory reduction caused by silently dropping images is a failed experiment, not a success.

## Risks / Trade-offs

- [Risk] Media references can outlive their files. → Keep content hashes and metadata, report a bounded placeholder on misses, and add cleanup/reconciliation diagnostics.
- [Risk] Existing plugins may assume persisted `image_url` always contains a data URI. → Keep the dual reader and resolve references at the provider boundary; add compatibility tests for plugin/tool history.
- [Risk] Extra disk I/O can increase latency. → Resolve only selected images, cache prepared media by content hash within one request, and measure cold/warm latency separately.
- [Risk] Image conversion can use native memory invisible to `tracemalloc`. → Use an external RSS monitor and report both RSS and Python allocations.
- [Risk] A provider may have a smaller limit than the internal default. → Apply the effective provider limit during request preparation and preserve readable provider-specific errors.

## Migration Plan

1. Ship dual reading before new reference writing; factor switches belong in the experiment harness, not a new public rollout switch.
2. Run the ablation suite and compatibility tests before enabling reference writing by default.
3. Provide a dry-run migration report for old inline histories.
4. Migrate selected conversations only after media files and hashes are verified.
5. Before downgrading to a reader without reference support, stop writes and export/re-inline all reference-bearing histories into a verified backup, including conversations created after deployment. Merely disabling new writes does not make those records readable by old versions. Retain the media store until rollback verification completes.

## 兼容与资源生命周期约束

- 当前基线工作区提交为 `1a2492a09f8722a9abd813f6a65fb687d53c88c9`，位于此前功能分支，不等同于 issue 的 v4.28.1。实现前固定目标基线及依赖，另建 v4.28.1 只读复现环境；不能拿两个版本的路径混合计算收益。
- 新引用采用内部版本化图片部件，保留 image detail；对外 ProviderRequest 输入继续接受原来的路径、URL、data URI。新类型不得直接发送给远端 Provider。
- Plugin/第三方 Provider 的兼容出口必须解析引用后再调用现有接口；内置 Provider 和摘要 Provider 都纳入测试。给插件的兼容视图可能仍需分配 base64，这部分成本如实报告，不能声称所有消费者都已懒加载。
- 媒体文件采用内容哈希去重，先在同文件系统原子写入并核验，再提交消息引用。写入失败保持原会话不变；崩溃留下的未引用文件由维护命令处理。
- 媒体读取通过内部 ID 查询并限制路径；WebUI 使用带会话权限校验的图片端点，不公开数据目录或仅凭哈希授权。会话列表/详情只返回引用和预览地址，不批量还原 base64。
- 复用现有附件存储能力前核对其 WebChat 删除逻辑，禁止把 Agent 媒体直接挂入会被其他界面独立删除的生命周期。引用对象与消息内容绑定，跨会话去重不得带来跨会话读权限。
- 首版不做运行中自动垃圾回收。显式维护命令在停止写入后扫描全部保留会话，输出 dry-run，隔离未引用对象；读写中断、解析失败时停止删除。移除或压缩一个会话不能删除仍被其他会话引用的文件。
- 旧 inline 图片在普通读取时不转码、不改写；显式迁移只搬运原字节并核验哈希，不在迁移中夹带画质调整。历史包与媒体目录共同备份；导出保持自包含或附带媒体清单，导入必须校验引用。
- 本地资源异常不应被笼统吞掉再走同一大请求；测试检查 MemoryError 保留异常类型并终止本次运行。413 与资源耗尽分开记录，不假设每个回退 Provider 的上限都相同，不引入自动多轮重压缩循环。
- 这不是对话事件日志重构；当前正常上下文压缩及保存行为保持不变。媒体表示迁移与“保留所有原始对话”的产品需求不得混为一谈。

## 详细内存消融实验

### 因素与对照

三个开关仅供实验调用真实生产函数，不提供给用户。完整八组为 `000 / A00 / 0B0 / 00C / AB0 / A0C / 0BC / ABC`。

| 因素 | 唯一变化 | 必须保持不变 |
| --- | --- | --- |
| A 统一入口 | 所有来源进入同一准备链 | 使用原压缩算法和参数 |
| B 懒加载 | 同一准备结果外置存储，选窗后加载 | 图片字节、MIME、顺序、detail、消息位置 |
| C 压缩优化 | 仅在基线已有入口改变压缩算法 | 不顺便补齐工具/插件入口 |

八组的零开关路径必须与固定基线的输入输出一致；用独立基线 checkout 的相同函数校验，不能把一个近似模拟器叫基线。另加纯文本对照，但不把它算作三因素收益。

### 固定样本

五类图片各包含普通与压力样本，每类三个固定种子，至少 30 个实例。文件在测量进程外生成，记录 SHA256、编码格式、尺寸、方向、透明度、帧数和字节数。

| 类别 | 普通 | 压力 |
| --- | --- | --- |
| PNG | 透明图/色块 | 1280×1280 高熵 RGBA，像素合规但字节超限 |
| JPEG | 常见照片、已压缩小文件 | 4000×3000 高细节、EXIF 旋转 |
| WebP | 静态有损 | 无损透明，动画分支另做覆盖 |
| GIF | 少帧动画 | 多帧动画，检查帧抽取/拼图峰值 |
| 工具截图 | 1920×1080 终端 | 4K 小字 UI 与坐标标记 |

来源测试覆盖本地文件、HTTP、data URI、base64 URI，以及用户附件、引用、插件/MCP、FileRead、CUA。HTTP 使用本地服务器；这些入口调用现有适配代码，不能仅给同一函数贴不同来源名称。完整交叉用于单图工作负载，其余长会话用五种格式均衡混合。

### 工作负载

1. 单图单轮、同轮八张不同图片；分别统计每个阶段。
2. 50 轮每轮一张不同图片，然后 20 轮纯文本；与重复同一张图片的独立测试区分去重收益。
3. 10/50/100 张历史图；分别测全在窗口、按轮次裁剪、摘要成功和摘要失败四种状态。记录实际触发次数，不假设默认配置一定触发。
4. 摘要模型分别支持和不支持图片。固定摘要返回值及用量，避免随机文本干扰；摘要图像输入遵循实际模态规则。
5. 四会话并发、保存后重启、WebUI 只看详情/展开单张预览、显式导出；WebUI 与模型请求分别统计。
6. 错误实验：缺失媒体、坏图片、取消、超时、写盘失败、5 MiB 聚合请求拒绝、独立单图限制、不同限制的回退 Provider。
7. 静态图片循环固定窗口请求 200 次，记录 1/10/25/50/100/200 次，检查存活对象、临时文件、打开句柄及运行后残留；不强制 GC 的正常数据与诊断 GC 分开。

### 测量与防止实验污染

- 分阶段打点：读取数据库 → JSON 解析/消息构造 → 选窗 → 读取媒体 → 解码/缩放/编码 → base64 → Provider 组装 → HTTP 序列化/发送 → 保存 → 清理。另标记摘要请求阶段。
- 记录原文件与输出文件字节、base64 长度、完整 HTTP JSON 字节、读取/解码/转码/base64 次数及字节量、阶段耗时、临时文件和持久化字节。磁盘数据不等价于内存收益。
- 外部监测进程每 10 ms 采集被测进程及子进程 RSS；记录 OS 高水位。Windows 另采私有内存与工作集。两个平台单独比较，不直接比较绝对值。
- 标准轮关闭 tracemalloc；诊断轮单独启用 tracemalloc，Linux 关键图另外追踪原生分配。先前约 24 MB WebP 结果缺乏初始化隔离，不能用作验收基线。
- 每个实验单元十次独立进程运行，冷启动/预热三次后的热运行分别记录。按种子配对，随机交错八组，保存完整运行顺序。固定机器、解释器、依赖和处理并发数。
- 本地模型服务返回固定文本、固定用量和固定摘要；真实客户端/SDK 必须参与最终请求组装。服务端流式计数，不保留所有历史请求体；结构校验另跑，不污染测量峰值。
- 监测器不拷贝 base64、不输出原图、会话正文或密钥。样本生成、结果分析和监测服务不得计入被测进程。
- 单次 120 秒或被测进程总内存达到 `min(2 GiB, 启动时可用内存的 25%)` 时停止并记录超限。崩溃、超时、OOM 数据不得丢弃或用零内存填充。

### 分析和验收

- 单因素效果比较 A/B/C 与基线，边际效果比较 ABC 与 BC/AC/AB；报告配对中位差、范围与原始样本，不把三个百分比相加。十次重复不宣称精确的 P99。
- B-only 校验图片哈希、顺序、detail 和固定 Provider 的历史前缀；预期最终请求大小不变。请求时仍需装载整个有效图片窗口，必须披露这个下限。
- C 校验方向、透明、截图文字和坐标；已合规原字节应原样保留，不能选用无必要膨胀的输出。超限失败不算“成功压缩”或内存收益。
- CUA 的尺寸和坐标必须一致；失败不能伪装成空图成功。GIF 的既有抽帧语义必须一致。
- B 在 50 张历史图的读取到选窗阶段，以相同消息窗口为前提，峰值增量降低至少 50%；ABC 在高熵长会话的成功可比场景中，整体峰值增量降低至少 30%。这是验收目标，不是已证明结果。
- 小图正常场景峰值增量及中位耗时回退不超过 10%；图片质量或稳定历史前缀失败时，即使内存达标也不通过。
- 持续请求后存活图片对象、文件句柄、临时文件不能按轮数线性增长。RSS 分配器保留不直接判定泄漏；结合对象与原生分配数据解释。
- 实测平台最低覆盖 Linux/WSL 与原生 Windows，macOS 做功能回归。所有指标原始 JSONL/CSV、样本清单和曲线放在测试产物目录，不创建仓库 SUMMARY 报告。
- 真实智谱只用于可选小样本画质/协议验证，与消融数据隔离。默认不发公网请求；密钥通过安全环境注入，绝不写入本规划或测试产物。
