# 新的 Agent 上下文存储架构

## 现状



AstrBot 默认使用 SQLite（`data_v4.db`），通过 SQLModel / SQLAlchemy 和 aiosqlite 访问，启用 WAL。



- 一个 UMO（`platform_name:message_type:session_id`）可以对应多个 Conversation，并选择当前对话。

- `ConversationV2.content` 保存整份模型消息数组。Manager 为兼容旧接口，又将其转换为 `Conversation.history` JSON 字符串。

- 内置 Agent 主要按“读取完整历史 → 在内存中修改、压缩 → 整体覆盖保存”工作。压缩后的内容会替代原历史。 

- 平台可见消息另存于 `platform_message_history`。内部 checkpoint 用于关联平台消息与上下文轮次，不是执行快照；WebChat 侧边对话目前通过复制历史实现。

- 插件可以直接修改上下文；保存上下文时会过滤 `_no_save` 内容。执行状态主要在内存中，数据库写入缺少统一的并发版本校验。

    

## 目标与边界

以不可变事件保存消息与执行记录，按当前分支投影出模型需要的上下文。支持长期不切换对话的大事件量、消息编辑、侧边对话，以及旧插件兼容。

**事件 append\-only；ConversationV3 的当前指针和元数据可以更新。** 上下文恢复不重新调用模型、工具或插件，也不等于自动恢复外部工具执行。



## 表结构

### ConversationV3

|字段|类型|用途|
|---|---|---|
|`id`|INTEGER，主键|数据库内部标识|
|`conversation_id`|UUID，唯一|对外稳定标识|
|`platform_id`|TEXT|平台实例标识|
|`umo`|TEXT<br>|当前会话归属，替代含义不清的 `user_id`|
|`title`|TEXT，可空|对话标题|
|`persona_id`|TEXT，可空|当前人格配置|
|`head_seq`|BIGINT，默认 0|本对话已提交的最大事件序号|
|`leaf_event_id`|UUID，可空|当前选中分支的上下文末端|
|`replay_from_event_id`|UUID，可空|当前分支上可直接恢复的 `context.rebased` 节点|
|`created_at`|UTC 时间|创建时间|
|`updated_at`|UTC 时间|最近业务更新时间|



不再保存 `content`；token 用量放在请求事件中。`umo` 暂时表达现有归属关系，每轮触发仍记录实际 UMO，为未来多 UMO 共用对话保留信息。



`replay_from_event_id` 是可重建的优化指针，不是另一份执行 checkpoint。使用全局事件 ID，是因为侧边对话可能继承另一 Conversation 的恢复起点，而 `seq` 只在各自对话内唯一。



### ConversationEvent

所有用户、所有对话的事件共用一张表，通过 `conversation_ref` 隔离查询。

|字段|类型|用途|
|---|---|---|
|`conversation_ref`|INTEGER，外键|指向 `ConversationV3.id`|
|`seq`|BIGINT，正整数|对话内递增序号，不因清空上下文而重置|
|`event_id`|UUID，唯一|全局事件身份，写入重试复用同一个 ID|
|`parent_event_id`|UUID，可空，外键|上下文父节点，可跨 Conversation；空值表示无父节点|
|`type`|TEXT|事件类型|
|`version`|INTEGER，默认 1|对应类型的 payload 版本|
|`payload`|JSON|类型专属数据|
|`created_at`|UTC 时间|记录时间，排序以 seq 为准|



约束与索引：

- 主键 `(conversation_ref, seq)`，唯一索引 `event_id`。

- 外键保证引用存在；跨会话引用还需校验访问权限，不能级联删除被其他分支引用的事件。

- parent 只能引用已存在的上下文节点，或同批次中更早的上下文节点，避免形成环。

- 插件按类型查询需要时，增加 `(conversation_ref, type, seq)` 索引。不默认索引整个 payload。

    

## 分支、读取与并发

只有 `message.appended` 和 `context.rebased` 构成上下文 parent 链；会话、执行和插件私有事件不推进上下文 leaf，执行关联使用 payload 中的 ID。

```Plain Text
原分支：m1 → m2 → m3 → m4
编辑后：m1 → m2 → m5 → m6
```



编辑产生新节点，原分支保留。侧边 Conversation 的首个上下文节点可以指向来源 Conversation 的节点。`seq` 表示本对话的写入顺序，不表示当前分支顺序，不能直接按 seq 范围把所有消息拼起来。

写入 API 可以省略 parent，表示接到当前 leaf；**落库必须写入解析后的真实父节点，不能用 NULL 表示“上一个事件”**。显式 NULL 表示新根。

切换分支直接更新 `leaf_event_id` 和对应的恢复指针，不增加 `branch.selected` 事件。因此日志不记录用户每次选择分支的操作历史。



长对话的处理：

1. 从当前 leaf 沿 parent 找到有效 rebase，批量或通过递归查询取得路径，再按正向顺序投影；避免每个父节点一次数据库往返。

2. rebase 保存完整有效上下文，恢复时不必读取其之前的祖先；旧历史仍可单独分页查询。

3. 按 token 预算压缩上下文；即使不需要摘要，也可以在重放事件数或字节量过大时追加内容不变的 rebase。

4. 按明确游标分页（如 `seq > after_seq`），不用不断扩大的 OFFSET，也不用记忆上次 LIMIT 来猜恢复范围。媒体使用资源引用。

5. 内存只缓存活跃分支的有效投影。不能因为有恢复指针，就假设永远没有过长的尾部路径。

    

序号分配、事件插入和指针更新在同一事务内完成。提交校验预期 `head_seq` 和 `leaf_event_id`；模型响应绑定开始时的分支，不能落到用户后来切换的分支。异步生成 rebase 也必须检查来源状态是否变化。冲突不能通过重新执行有副作用的插件或工具来解决。



## 事件类型

|类型|含义|
|---|---|
|`conversation.created`|创建会话，记录初始元数据和可选分支来源|
|`conversation.updated`|修改标题、人格等会话属性|
|`message.appended`|追加用户、assistant、tool 等模型消息|
|`context.rebased`|建立新的完整上下文投影起点|
|`turn.started`|一轮 Agent 处理开始|
|`turn.finished`|整轮处理结束|
|`request.started`|一次实际模型请求尝试开始|
|`request.finished`|请求结束，记录状态、usage、输出引用或错误|
|`tool.started`|工具准备执行，记录实际参数|
|`tool.finished`|工具执行结束，记录结果引用或错误|
|`plugin.<plugin_id>.<event_type>`|插件私有记录，默认不参与模型上下文投影|



一轮 turn 可以包含多次 request 和工具执行。turn、request、工具执行实例分别使用其 started 事件的 `event_id` 作为身份。重试创建新的请求或执行实例。



### 对话

实际 ID 使用 UUID，以下用短 ID 示意；后续例子省略重复的公共字段。

```JSON
{
  "conversation_ref": 42,
  "seq": 1,
  "event_id": "e1",
  "parent_event_id": null,
  "type": "conversation.created",
  "version": 1,
  "payload": {
    "platform_id": "my_qq_bot",
    "umo": "my_qq_bot:FriendMessage:user_123",
    "persona_id": "default"
  },
  "created_at": "2026-09-13T10:00:00Z"
}
```



创建侧边对话时，payload 可增加 `forked_from_event_id`。更新属性时，字段缺席表示不修改，显式 null 表示清空：

```JSON
{
  "type": "conversation.updated",
  "payload": {"changes": {"title": "旅行计划", "persona_id": null}}
}
```



### 消息与 rebase



消息内容沿用 AstrBot 消息模型，保留工具调用、多模态内容以及供应商需要的额外字段。下面以常见消息格式示意：

```JSON
[
  {
    "event_id": "m1",
    "parent_event_id": null,
    "type": "message.appended",
    "payload": {
      "turn_id": "t1",
      "message": {"role": "user", "content": "查一下北京天气"}
    }
  },
  {
    "event_id": "m2",
    "parent_event_id": "m1",
    "type": "message.appended",
    "payload": {
      "turn_id": "t1",
      "request_id": "r1",
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [{
          "id": "call_1",
          "type": "function",
          "function": {"name": "get_weather", "arguments": "{\"city\":\"北京\"}"}
        }]
      }
    }
  },
  {
    "event_id": "m3",
    "parent_event_id": "m2",
    "type": "message.appended",
    "payload": {
      "turn_id": "t1",
      "message": {"role": "tool", "tool_call_id": "call_1", "content": "北京晴，25°C"}
    }
  }
]
```



`context.rebased` 统一使用 `reason` 区分 `compaction`、`reset`、`legacy_replace`、`migration` 和 `snapshot`。messages 是完整有效列表；如有其他继续投影所需的状态，也必须随事件保存。仅保存旧消息 ID 而需要扫描古老历史补齐内容，不能算完整恢复起点。



```JSON
{
  "event_id": "b1",
  "parent_event_id": "m100",
  "type": "context.rebased",
  "payload": {
    "reason": "compaction",
    "messages": [
      {"id": "mxxx", "message": {"role": "system", "content": "xxxxxx"}},
      {"id": "summary_b1", "message": {"role": "user", "content": "此前摘要：用户计划周末去北京。"}},
      {"id": "m99", "message": {"role": "user", "content": "如果下雨呢？"}},
      {"id": "m100", "message": {"role": "assistant", "content": "可以参观室内博物馆。"}}
    ]
  }
}
```



保留消息沿用消息身份，新摘要分配新身份；消息 ID 不一定是独立事件外键。摘要角色与顺序由压缩策略决定。reset 使用空列表；snapshot 保持消息内容和顺序不变。优先在无待处理工具调用的稳定边界生成 rebase。



### turn、request 与 tool



下面是各类型的独立示例，不是完整执行顺序：

```JSON
[
  {
    "event_id": "t1",
    "type": "turn.started",
    "payload": {
      "trigger": {"kind": "im_wake", "umo": "my_qq_bot:FriendMessage:user_123", "message_id": "platform_msg_1"},
      "base_leaf_event_id": null
    }
  },
  {
    "type": "turn.finished",
    "payload": {"turn_id": "t1", "status": "completed"}
  },
  {
    "event_id": "r1",
    "type": "request.started",
    "payload": {
      "turn_id": "t1",
      "context_leaf_event_id": "m1",
      "provider_id": "configured_provider_1",
      "model": "configured_model",
      "parameters": {"temperature": 0.7}
    }
  },
  {
    "type": "request.finished",
    "payload": {
      "request_id": "r1",
      "status": "completed",
      "output_event_ids": ["m2"],
      "finish_reason": "tool_calls",
      "usage": {"input_tokens": 1200, "output_tokens": 80, "cached_input_tokens": 600}
    }
  },
  {
    "event_id": "x1",
    "type": "tool.started",
    "payload": {
      "turn_id": "t1",
      "tool_call_id": "call_1",
      "tool_name": "get_weather",
      "arguments": {"city": "北京", "units": "celsius"}
    }
  },
  {
    "type": "tool.finished",
    "payload": {"execution_id": "x1", "status": "completed", "result_event_id": "m3"}
  }
]
```



执行约定：

- turn\.trigger 按来源提供字段，可为 `im_wake`、`plugin`、`agent`、`background_task_finished` 等，不填无意义的空字段。

- finished 用 `status` 区分 `completed`、`failed`、`cancelled`；失败可附 `error: {code, message}`。只有 started 表示结果未知，不能据此自动重试外部操作。

- `request.finished.usage` 是用量权威明细；turn 可保存汇总。

- `tool.started` 在执行前提交，记录插件 hook 处理后的实际参数。模型提出的 tool\_calls 不等于工具实际执行。

- finished 和对应消息可一起提交；执行结果与模型可见结果相同时使用引用，发生改写时分别保留必要内容，避免错误引用或重复大正文。

- 不默认逐条存储 token delta、工具进度和 hook 通知。崩溃恢复外部副作用还需要幂等或结果查询机制。

- `_no_save` 定义为：**内容照旧落盘，但是通过字段控制不进入投影。**

    ```JSON
    {
      "type": "message.appended",
      "payload": {
        **"include_in_context": false,**
        "message": {
          "role": "user",
          "content": "仅供本次请求使用的临时提示"
        }
      }
    }
    ```

## 插件接口与兼容



旧插件继续使用原有的可变 `ProviderRequest.contexts`、运行时消息对象和 ConversationManager 接口。核心事件保持不可变，插件拿到与持久化状态隔离的工作副本；同一阶段的插件按顺序看到前面插件的修改。



兼容层在原有保存边界比较阶段输入与最终输出，不对每个插件复制整份历史：



- 无变化：不产生上下文事件。

- 原消息前缀不变、只追加：生成 `message.appended`。

- 删除、重排、嵌套修改或整体替换：生成 `context.rebased(reason=legacy_replace)`。



插件在已绑定会话的 hook 中，通过 ConversationManager 获取统一接口：

```Python
events = ctx.conversation_manager.get_conversation_events()
await events.append_message({"role": "user", "content": "补充上下文"})
await events.append(
    name="retrieval_completed",
    payload={"document_ids": ["doc_12", "doc_35"]},
)
previous = await events.latest(name="retrieval_completed")
page = await events.list(name="retrieval_completed", after_seq=last_seq, limit=100)
```



框架绑定插件身份与会话、分配 ID 和 seq、校验 JSON 并落库，生成例如：

```JSON
{
  "event_id": "p1",
  "type": "plugin.astrbot_plugin_memory.retrieval_completed",
  "payload": {"turn_id": "t1", "document_ids": ["doc_12", "doc_35"], "scores": [0.91, 0.86]}
}
```



插件日志默认按当前 Conversation 和插件身份查询，不自动继承来源分支的插件状态；分支相关记录显式关联上下文事件 ID。插件私有记录不驱动核心消息投影，卸载插件也不影响核心上下文恢复。



想永久改变上下文，应调用核心追加消息或替换上下文接口；只给当前请求提供检索内容，则使用明确的临时请求接口。恢复时读取已记录的结果，不重新执行插件业务逻辑。


