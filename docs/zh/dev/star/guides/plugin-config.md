# 插件配置

Star 可以在插件根目录提供 `_conf_schema.json`。AstrBot 会根据 schema 创建插件配置文件、在 WebUI 渲染表单，并在插件实例化时注入 `AstrBotConfig`。

Schema 文件必须是**严格 JSON**，不能包含注释、尾随逗号或 Python 的 `True` / `False`。

## 最小 schema

```json
{
  "token": {
    "description": "Service token",
    "type": "string",
    "obvious_hint": true
  },
  "timeout": {
    "description": "Request timeout in seconds",
    "type": "int",
    "default": 30,
    "slider": {
      "min": 1,
      "max": 120,
      "step": 1
    }
  },
  "advanced": {
    "description": "Advanced settings",
    "type": "object",
    "items": {
      "enabled": {
        "type": "bool",
        "default": false
      }
    }
  }
}
```

## 支持的类型

当前运行时支持：

| `type`          | 默认值  | WebUI / 存储语义                           |
| --------------- | ------- | ------------------------------------------ |
| `string`        | `""`    | 单行字符串。                               |
| `text`          | `""`    | 多行文本。                                 |
| `int`           | `0`     | 整数；可配 `slider`。                      |
| `float`         | `0.0`   | 浮点数；可配 `slider`。                    |
| `bool`          | `false` | 开关。                                     |
| `list`          | `[]`    | JSON 数组；可用 `items` 描述对象数组元素。 |
| `file`          | `[]`    | 上传文件后保存相对路径字符串列表。         |
| `object`        | `{}`    | 嵌套对象，必须提供 `items`。               |
| `dict`          | `{}`    | 开放式键值对象，可在 WebUI 中编辑。        |
| `template_list` | `[]`    | 从预定义模板创建的对象列表。               |

`dict` 是开放式键值对象。WebUI 会提供键值编辑器；使用 `items: {}` 可编辑任意键值，需要预置字段和类型时可以增加 `template_schema`。如果插件需要固定的结构化 schema，应使用明确 `items` 的 `object`。除编辑器元数据外的值校验仍由插件负责。

## 通用元数据

- `description`：字段名称或简短说明。
- `hint`：补充帮助文本。
- `obvious_hint`：让 hint 在表单中醒目显示。
- `default`：明确默认值；类型必须与 `type` 一致。
- `invisible`：从 WebUI 隐藏，但仍存在于配置中。
- `options`：字符串/数值选项列表，渲染为选择器。
- `labels`：与 `options` 一一对应的显示文本。国际化限制见[插件国际化](./plugin-i18n)。
- `slider`：只用于 `int` / `float`，对象包含 `min`、`max`、`step`。
- `editor_mode`、`editor_language`、`editor_theme`：为文本/结构化输入启用代码编辑器。
- `_special`：使用 AstrBot 提供的动态选择器。

在 WebUI 编辑插件配置时，已修改且可写的字段可恢复为此 schema 默认值。该控件只用于插件配置，不会出现在 Core 设置中。`object` 类型会从 `items` 递归构造恢复值，object 自身的 `default` 不会覆盖这一结构；未知类型和 `readonly` 字段不会显示恢复控件。

插件可稳定使用的常见 `_special` 值包括：

- `select_provider`、`select_provider_tts`、`select_provider_stt`：返回 Provider ID 字符串；
- `select_persona`：返回 Persona ID 字符串；
- `select_knowledgebase`：返回知识库 ID 列表，对应字段应为 `list`。

Core 内部还使用其他 `_special` 值，但它们不是插件 SDK 契约，不要从核心配置复制。

## 文件上传字段

```json
{
  "reference_files": {
    "type": "file",
    "description": "Reference documents",
    "default": [],
    "file_types": ["pdf", "txt", "md"]
  }
}
```

上传结果不是绝对路径，而是类似下面的字符串列表：

```json
{
  "reference_files": ["files/reference_files/guide.pdf"]
}
```

文件保存在 `data/plugin_data/<plugin-root>/files/<config-key>/`。路径会经过目录和扩展名校验，单文件上限当前为 500 MiB。插件中用公开存储入口解析：

```python
absolute_path = self.context.storage.data_directory() / config["reference_files"][0]
```

不要把上传路径当作 URL，也不要绕过相对路径校验访问其他插件的数据。

## `template_list`

`template_list` 适合让用户从多个固定结构中添加任意数量的条目：

```json
{
  "endpoints": {
    "type": "template_list",
    "description": "Endpoints",
    "templates": {
      "http": {
        "name": "HTTP endpoint",
        "display_item": "name",
        "items": {
          "name": {
            "type": "string",
            "default": ""
          },
          "url": {
            "type": "string",
            "default": "https://example.com"
          },
          "timeout": {
            "type": "int",
            "default": 30
          }
        }
      }
    }
  }
}
```

保存值包含模板标识：

```json
{
  "endpoints": [
    {
      "__template_key": "http",
      "name": "primary",
      "url": "https://example.com",
      "timeout": 30
    }
  ]
}
```

- `display_item` 指向一个用于折叠列表标题的字段，也支持 `meta.name` 形式的嵌套路径。
- `hide_hint_in_list: true` 只隐藏条目折叠列表中的模板 hint。
- 每个模板都必须有 `items`，保存值会按所选模板递归校验。

## 在插件中接收配置

```python
from astrbot.api import AstrBotConfig
from astrbot.api.star import PluginContext, Star


class Main(Star):
    def __init__(self, context: PluginContext, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config

    async def initialize(self) -> None:
        timeout = int(self.config["timeout"])
        # Initialize clients with validated configuration.
        _ = timeout
```

插件配置文件名取自插件目录的 root name，保存为 `data/config/<root-name>_config.json`，不是 metadata 中任意显示名称。WebUI 保存后会校验数据、写入配置并重载插件；因此所有 client、任务和文件都必须在 `terminate()` 中正确清理。

插件确实需要在异步处理器中更新配置时，可以修改 `self.config` 后 `await self.config.save_config_async()`。不要在每条消息中频繁写盘，也不要把运行状态、缓存或用户数据塞进配置；这些数据应放入 [插件存储](./storage)。

## Schema 更新规则

加载新版本时，AstrBot 会按 schema 补齐缺失默认值、调整结构，并移除已经不存在的字段。发布 schema 变更时：

1. 保持同一键的类型稳定，或在插件初始化中执行明确迁移；
2. 不要依赖已经从 schema 删除的隐藏字段继续保存数据；
3. 用真实 JSON 解析 `_conf_schema.json`；
4. 在空配置、旧配置和 WebUI 保存/重载三条路径上测试；
5. secret 字段不要写入日志、示例或错误详情。
