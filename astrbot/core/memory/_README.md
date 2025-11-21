## Decay Score

记忆衰减分数定义为：

\[
\text{decay\_score}
= \alpha \cdot e^{-\lambda \cdot \Delta t \cdot \beta}

+ (1-\alpha)\cdot (1 - e^{-\gamma \cdot c})
\]

其中：

+ \(\Delta t\)：自上次检索以来经过的时间（天），由 `last_retrieval_at` 计算；
+ \(c\)：检索次数，对应字段 `retrieval_count`；
+ \(\alpha\)：控制时间衰减和检索次数影响的权重；
+ \(\gamma\)：控制检索次数影响的速率；
+ \(\lambda\)：控制时间衰减的速率；
+ \(\beta\)：时间衰减调节因子；

\[
\beta = \frac{1}{1 + a \cdot c}
\]

+ \(a\)：控制检索次数对时间衰减影响的权重。

## ADD MEMORY

+ LLM 通过 `astr_add_memory` 工具调用，传入记忆内容和记忆类型。
+ 生成 `mem_id = uuid4()`。
+ 从上下文中获取 `owner_id = unified_message_origin`。

步骤：

1. 使用 VecDB 以新记忆内容为 query，检索前 20 条相似记忆。
2. 从中取相似度最高的前 5 条：
   + 若相似度超过“合并阈值”（如 `sim >= merge_threshold`）：
     + 将该条记忆视为同一记忆，使用 LLM 将旧内容与新内容合并；
     + 在同一个 `mem_id` 上更新 MemoryDB 和 VecDB（UPDATE，而非新建）。
   + 否则：
     + 作为全新的记忆插入：
       + 写入 VecDB（metadata 中包含 `mem_id`, `owner_id`）；
       + 写入 MemoryDB 的 `memory_chunks` 表，初始化：
         + `created_at = now`
         + `last_retrieval_at = now`
         + `retrieval_count = 1` 等。
3. 对 VecDB 返回的前 20 条记忆，如果相似度高于某个“赫布阈值”（`hebb_threshold`），则：
   + `retrieval_count += 1`
   + `last_retrieval_at = now`

这一步体现了赫布学习：与新记忆共同被激活的旧记忆会获得一次强化。

## QUERY MEMORY (STATIC)

+ LLM 通过 `astr_query_memory` 工具调用，无参数。

步骤：

1. 从 MemoryDB 的 `memory_chunks` 表中查询当前用户所有活跃记忆：
   + `SELECT * FROM memory_chunks WHERE owner_id = ? AND is_active = 1`
2. 对每条记忆，根据 `last_retrieval_at` 和 `retrieval_count` 计算对应的 `decay_score`。
3. 按 `decay_score` 从高到低排序，返回前 `top_k` 条记忆内容给 LLM。
4. 对返回的这 `top_k` 条记忆：
   + `retrieval_count += 1`
   + `last_retrieval_at = now`

## QUERY MEMORY (DYNAMIC)（暂不实现）

+ LLM 提供查询内容作为语义 query。
+ 使用 VecDB 检索与该 query 最相似的前 `N` 条记忆（`N > top_k`）。
+ 根据 `mem_id` 从 `memory_chunks` 中加载对应记录。
+ 对这批候选记忆计算：
  + 语义相似度（来自 VecDB）
  + `decay_score`
  + 最终排序分数（例如 `w1 * sim + w2 * decay_score`）
+ 按最终排序分数从高到低返回前 `top_k` 条记忆内容，并更新它们的 `retrieval_count` 和 `last_retrieval_at`。
