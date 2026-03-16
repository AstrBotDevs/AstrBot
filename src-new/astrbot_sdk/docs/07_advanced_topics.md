# AstrBot SDK 高级主题

本文档介绍 AstrBot SDK 的高级用法，包括并发处理、性能优化、安全最佳实践和架构设计。

## 目录

- [并发处理](#并发处理)
- [性能优化](#性能优化)
- [安全最佳实践](#安全最佳实践)
- [架构设计模式](#架构设计模式)
- [高级客户端用法](#高级客户端用法)

---

## 并发处理

### asyncio 基础

SDK 完全基于 asyncio 构建，所有操作都是异步的。

```python
import asyncio
from astrbot_sdk import Star, Context, MessageEvent
from astrbot_sdk.decorators import on_command

class MyPlugin(Star):
    @on_command("concurrent")
    async def concurrent_handler(self, event: MessageEvent, ctx: Context):
        # 并发执行多个操作
        tasks = [
            ctx.llm.chat("任务1"),
            ctx.llm.chat("任务2"),
            ctx.llm.chat("任务3"),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                await event.reply(f"任务{i+1}失败: {result}")
            else:
                await event.reply(f"任务{i+1}结果: {result}")
```

### 并发限制

避免同时发起过多请求：

```python
import asyncio
from asyncio import Semaphore

class MyPlugin(Star):
    def __init__(self):
        # 限制并发数
        self._semaphore = Semaphore(5)
    
    async def limited_operation(self, ctx, prompt):
        async with self._semaphore:
            return await ctx.llm.chat(prompt)
    
    @on_command("batch")
    async def batch_handler(self, event: MessageEvent, ctx: Context):
        prompts = ["任务1", "任务2", "任务3", "任务4", "任务5"]
        
        # 使用 semaphore 限制并发
        tasks = [self.limited_operation(ctx, p) for p in prompts]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        await event.reply(f"完成 {len(results)} 个任务")
```

### 取消处理

正确处理操作取消：

```python
@on_command("cancelable")
async def cancelable_handler(self, event: MessageEvent, ctx: Context):
    try:
        # 长时间运行的操作
        for i in range(100):
            # 检查是否被取消
            ctx.cancel_token.raise_if_cancelled()
            
            await asyncio.sleep(0.1)
            
            if i % 10 == 0:
                await event.reply(f"进度: {i}%")
        
        await event.reply("完成！")
    except asyncio.CancelledError:
        await event.reply("操作已取消")
        raise  # 重新抛出以便框架处理
```

### 锁和同步

保护共享资源：

```python
import asyncio

class MyPlugin(Star):
    def __init__(self):
        self._lock = asyncio.Lock()
        self._counter = 0
    
    async def increment(self):
        async with self._lock:
            # 临界区
            current = self._counter
            await asyncio.sleep(0.1)  # 模拟操作
            self._counter = current + 1
            return self._counter
    
    @on_command("count")
    async def count_handler(self, event: MessageEvent, ctx: Context):
        count = await self.increment()
        await event.reply(f"当前计数: {count}")
```

---

## 性能优化

### 1. 连接池

复用 HTTP 连接：

```python
import aiohttp

class MyPlugin(Star):
    async def on_start(self, ctx):
        # 创建连接池
        self._session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=20)
        )
    
    async def on_stop(self, ctx):
        await self._session.close()
    
    async def fetch_data(self, url):
        # 复用连接
        async with self._session.get(url) as response:
            return await response.json()
```

### 2. 缓存策略

使用内存缓存减少重复计算：

```python
from functools import lru_cache
import asyncio

class MyPlugin(Star):
    def __init__(self):
        self._cache = {}
        self._cache_lock = asyncio.Lock()
    
    async def get_cached_data(self, key, ttl=300):
        async with self._cache_lock:
            if key in self._cache:
                data, timestamp = self._cache[key]
                if asyncio.get_event_loop().time() - timestamp < ttl:
                    return data
        
        # 从数据库获取
        data = await self.fetch_from_db(key)
        
        async with self._cache_lock:
            self._cache[key] = (data, asyncio.get_event_loop().time())
        
        return data
    
    async def invalidate_cache(self, key):
        async with self._cache_lock:
            self._cache.pop(key, None)
```

### 3. 批处理

批量操作减少网络往返：

```python
@on_command("batch_db")
async def batch_db_handler(self, event: MessageEvent, ctx: Context):
    # 批量获取
    keys = [f"user:{i}" for i in range(100)]
    values = await ctx.db.get_many(keys)
    
    # 批量设置
    updates = {f"user:{i}": {"updated": True} for i in range(100)}
    await ctx.db.set_many(updates)
    
    await event.reply(f"更新了 {len(updates)} 条记录")
```

### 4. 流式处理

使用流式 API 处理大数据：

```python
@on_command("stream")
async def stream_handler(self, event: MessageEvent, ctx: Context):
    # 流式 LLM 响应
    message = await event.reply("正在生成...")
    
    full_text = ""
    async for chunk in ctx.llm.stream_chat("写一个很长的故事"):
        full_text += chunk
        # 每 100 个字符更新一次
        if len(full_text) % 100 < 10:
            await message.edit(full_text + "...")
    
    await message.edit(full_text)
```

### 5. 懒加载

延迟初始化资源：

```python
class MyPlugin(Star):
    def __init__(self):
        self._expensive_resource = None
        self._resource_lock = asyncio.Lock()
    
    async def get_resource(self):
        if self._expensive_resource is None:
            async with self._resource_lock:
                if self._expensive_resource is None:
                    # 昂贵的初始化
                    self._expensive_resource = await self.init_resource()
        return self._expensive_resource
```

---

## 安全最佳实践

### 1. 输入验证

始终验证用户输入：

```python
import re
from astrbot_sdk.errors import AstrBotError

@on_command("search")
async def search_handler(self, event: MessageEvent, ctx: Context, query: str):
    # 验证输入长度
    if len(query) > 1000:
        raise AstrBotError.invalid_input("查询过长，最多 1000 字符")
    
    # 验证输入内容
    if not re.match(r'^[\w\s\-]+$', query):
        raise AstrBotError.invalid_input("查询包含非法字符")
    
    # 执行搜索
    result = await self.search(query)
    await event.reply(result)
```

### 2. 防止注入攻击

```python
# 危险的代码
# await ctx.db.set(f"user:{event.user_id}", eval(user_input))

# 安全的代码
import json

@on_command("save")
async def save_handler(self, event: MessageEvent, ctx: Context, data: str):
    try:
        # 使用 JSON 解析而不是 eval
        parsed = json.loads(data)
        await ctx.db.set(f"user:{event.user_id}", parsed)
    except json.JSONDecodeError:
        raise AstrBotError.invalid_input("无效的 JSON 格式")
```

### 3. 敏感信息处理

```python
import os

class MyPlugin(Star):
    async def on_start(self, ctx):
        config = await ctx.metadata.get_plugin_config()
        
        # 从配置或环境变量获取敏感信息
        self.api_key = config.get("api_key") or os.getenv("MY_PLUGIN_API_KEY")
        
        if not self.api_key:
            raise ValueError("缺少 API Key")
        
        # 不要在日志中打印敏感信息
        ctx.logger.info("API Key 已配置")
        # 不要: ctx.logger.info(f"API Key: {self.api_key}")
```

### 4. 权限检查

```python
from astrbot_sdk.decorators import require_admin

class MyPlugin(Star):
    @on_command("admin_only")
    @require_admin
    async def admin_only(self, event: MessageEvent, ctx: Context):
        await event.reply("管理员命令执行成功")
    
    async def check_permission(self, event, required_role):
        # 自定义权限检查
        if not event.is_admin() and required_role == "admin":
            raise AstrBotError.invalid_input("需要管理员权限")
```

### 5. 速率限制

```python
from astrbot_sdk.decorators import rate_limit

class MyPlugin(Star):
    @on_command("expensive")
    @rate_limit(
        limit=5,
        window=3600,
        scope="user",
        message="每小时只能调用 5 次"
    )
    async def expensive_operation(self, event: MessageEvent, ctx: Context):
        # 昂贵的操作
        result = await ctx.llm.chat("复杂任务", model="gpt-4")
        await event.reply(result)
```

---

## 架构设计模式

### 1. 分层架构

```
my_plugin/
├── __init__.py
├── main.py              # 插件入口
├── handlers/            # 处理器层
│   ├── __init__.py
│   ├── commands.py      # 命令处理器
│   └── messages.py      # 消息处理器
├── services/            # 业务逻辑层
│   ├── __init__.py
│   ├── user_service.py
│   └── data_service.py
├── models/              # 数据模型层
│   ├── __init__.py
│   └── user.py
└── utils/               # 工具层
    ├── __init__.py
    └── helpers.py
```

### 2. 依赖注入

```python
class UserService:
    def __init__(self, ctx: Context):
        self._ctx = ctx
    
    async def get_user(self, user_id: str):
        return await self._ctx.db.get(f"user:{user_id}")

class MyPlugin(Star):
    async def on_start(self, ctx):
        # 注入依赖
        self._user_service = UserService(ctx)
    
    @on_command("profile")
    async def profile_handler(self, event: MessageEvent, ctx: Context):
        user = await self._user_service.get_user(event.user_id)
        await event.reply(f"用户信息: {user}")
```

### 3. 事件驱动架构

```python
class MyPlugin(Star):
    def __init__(self):
        self._event_handlers = {}
    
    def register_handler(self, event_type, handler):
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    async def emit_event(self, event_type, data):
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                await handler(data)
            except Exception as e:
                self.logger.error(f"事件处理失败: {e}")
```

### 4. 状态机模式

```python
from enum import Enum, auto

class ConversationState(Enum):
    IDLE = auto()
    WAITING_INPUT = auto()
    PROCESSING = auto()

class MyPlugin(Star):
    def __init__(self):
        self._states = {}
    
    async def get_state(self, session_id):
        return self._states.get(session_id, ConversationState.IDLE)
    
    async def set_state(self, session_id, state):
        self._states[session_id] = state
    
    @on_message()
    async def handle_message(self, event: MessageEvent, ctx: Context):
        state = await self.get_state(event.session_id)
        
        if state == ConversationState.IDLE:
            await self.handle_idle(event, ctx)
        elif state == ConversationState.WAITING_INPUT:
            await self.handle_waiting(event, ctx)
```

---

## 高级客户端用法

### 1. ProviderManagerClient

```python
from astrbot_sdk import Star, Context
from astrbot_sdk.decorators import on_command

class MyPlugin(Star):
    @on_command("switch_provider")
    async def switch_provider(self, event: MessageEvent, ctx: Context):
        # 列出所有 Provider
        providers = await ctx.provider_manager.get_insts()
        
        # 切换 Provider
        await ctx.provider_manager.set_provider(
            provider_id="gpt-4",
            provider_type="chat_completion"
        )
        
        # 监听 Provider 变更
        async for change in ctx.provider_manager.watch_changes():
            ctx.logger.info(f"Provider 变更: {change.provider_id}")
```

### 2. 平台管理

```python
@on_command("platform_info")
async def platform_info(self, event: MessageEvent, ctx: Context):
    # 获取平台实例
    platform = await ctx.get_platform_inst("qq:instance1")
    
    if platform:
        await platform.refresh()
        await event.reply(
            f"平台: {platform.name}\n"
            f"状态: {platform.status}\n"
            f"错误数: {len(platform.errors)}"
        )
```

### 3. 高级 LLM 用法

```python
from astrbot_sdk.llm.entities import ProviderRequest

@on_command("advanced_llm")
async def advanced_llm(self, event: MessageEvent, ctx: Context):
    # 使用 ProviderRequest 进行精细控制
    request = ProviderRequest(
        prompt="生成内容",
        system_prompt="你是一个助手",
        temperature=0.7,
        max_tokens=2000
    )
    
    # 使用工具循环 Agent
    response = await ctx.tool_loop_agent(
        request=request,
        tool_names=["search", "calculate"]
    )
    
    await event.reply(response.text)
```

### 4. 会话管理

```python
from astrbot_sdk.conversation import ConversationSession

@on_command("conversation")
async def conversation_handler(self, event: MessageEvent, ctx: Context):
    # 创建会话
    session = ConversationSession(
        session_id=event.session_id,
        conversation_id="conv_123"
    )
    
    # 使用会话上下文
    async with session:
        await session.send("开始对话")
        response = await session.receive()
        await session.send(f"收到: {response}")
```

---

## 性能监控

### 1. 添加性能指标

```python
import time

class MyPlugin(Star):
    async def monitored_operation(self, operation, *args, **kwargs):
        start = time.time()
        try:
            result = await operation(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start
            self.logger.info(f"操作耗时: {duration:.2f}s")
    
    @on_command("slow")
    async def slow_handler(self, event: MessageEvent, ctx: Context):
        result = await self.monitored_operation(
            ctx.llm.chat,
            "复杂查询"
        )
        await event.reply(result)
```

### 2. 内存监控

```python
import sys
import gc

class MyPlugin(Star):
    def log_memory_usage(self):
        # 获取内存使用
        gc.collect()
        objects = gc.get_objects()
        self.logger.debug(f"当前对象数: {len(objects)}")
```

---

## 相关文档

- [错误处理与调试](./06_error_handling.md)
- [测试指南](./08_testing_guide.md)
- [安全检查清单](./11_security_checklist.md)
