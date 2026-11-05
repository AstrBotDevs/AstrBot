# 插件存储

## 简单 KV 存储

> [!TIP]
> 该功能需要 AstrBot 版本 >= 4.9.2。

插件可以使用 AstrBot 提供的简单 KV 存储功能来存储一些配置信息或临时数据。该存储是基于插件维度的，每个插件有独立的存储空间，互不干扰。

```py
class Main(star.Star):
    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        """Aloha!"""
        await self.put_kv_data("greeted", True)
        greeted = await self.get_kv_data("greeted", False)
        await self.delete_kv_data("greeted")
```

### 并发更新计数器

两个处理器可能都读到 `used = 4`，然后各自写回 `5`，这样就少计了一次。存储层会按入队顺序处理写入，但先调用 `get_kv_data`、再调用 `put_kv_data`，这两步合起来不具备原子性。

如果配额只在一个插件实例内使用，可以在 `__init__` 中创建一把锁，让所有修改计数器的处理器共用它。从读取计数、检查配额到写回结果，整个过程都要持有这把锁。

```py
import asyncio

from astrbot.api.star import Context, Star


class Main(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._quota_lock = asyncio.Lock()

    async def claim_slot(self, limit: int) -> bool:
        async with self._quota_lock:
            used = await self.get_kv_data("used", 0)
            if used >= limit:
                return False
            await self.put_kv_data("used", used + 1)
            return True
```

这把锁只对共享同一插件实例的任务有效。热重载时，旧实例的任务可能仍在运行，而新实例已经在使用另一把锁。不同进程也各有自己的锁。如果配额必须跨实例或进程生效，应使用能在同一事务中检查并更新计数器的存储。

## 存储大文件规范

为了规范插件存储大文件的行为，请将大文件存储于 `data/plugin_data/{plugin_name}/` 目录下。

你可以通过以下代码获取插件数据目录：

```py
from pathlib import Path
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

plugin_data_path = (
    Path(get_astrbot_data_path()) / "plugin_data" / self.name
)  # self.name 为插件名称，在 v4.9.2 及以上版本可用，低于此版本请自行指定插件名称
```
