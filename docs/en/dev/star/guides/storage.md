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


## Large File Storage Convention

To keep large file handling consistent, store large files under `data/plugin_data/{plugin_name}/`.

You can fetch the plugin data directory with:

```py
from pathlib import Path
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

plugin_data_path = Path(get_astrbot_data_path()) / "plugin_data" / self.name  # self.name is the plugin name; available in v4.9.2 and above. For lower versions, specify the plugin name yourself.
```
