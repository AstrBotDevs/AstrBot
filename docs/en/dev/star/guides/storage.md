# Plugin Storage

## Simple KV Storage

> [!TIP]
> Requires AstrBot version >= 4.9.2.

Plugins can use AstrBot's simple key-value store to persist configuration or temporary data. The storage is scoped per plugin, so each plugin has its own isolated space.

```py
class Main(star.Star):
    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        """Aloha!"""
        await self.put_kv_data("greeted", True)
        greeted = await self.get_kv_data("greeted", False)
        await self.delete_kv_data("greeted")
```

### Updating a shared counter

Two handlers can both read `used = 4` and both write `5`. The store processes queued writes in order, but a call to `get_kv_data` followed by `put_kv_data` is not an atomic update.

For a quota on one plugin instance, create one lock in `__init__` and use it everywhere that changes the counter. Hold it from the first read through the quota check and the write.

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

This lock only coordinates tasks that share the same plugin instance. On a hot reload, a task from the old instance may still be running while the new instance uses a different lock. Separate processes also have separate locks. If the quota must hold across instances or processes, use storage that can check and update the counter in a single transaction.

## Large File Storage Convention

To keep large file handling consistent, store large files under `data/plugin_data/{plugin_name}/`.

You can fetch the plugin data directory with:

```py
from pathlib import Path
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

plugin_data_path = (
    Path(get_astrbot_data_path()) / "plugin_data" / self.name
)  # self.name is the plugin name; available in v4.9.2 and above. For lower versions, specify the plugin name yourself.
```
