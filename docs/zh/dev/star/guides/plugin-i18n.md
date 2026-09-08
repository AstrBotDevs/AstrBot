# 插件国际化

插件可以在自己的目录下提供 `.astrbot-plugin/i18n/*.json`，让 WebUI 根据当前语言显示插件名称、描述和配置项文案。

## 目录结构

```text
your_plugin/
  metadata.yaml
  _conf_schema.json
  .astrbot-plugin/
    i18n/
      zh-CN.json
      en-US.json
```

语言文件名使用 WebUI 的 locale，例如 `zh-CN.json`、`en-US.json`。文件内容必须是 JSON object。

当当前语言没有对应翻译、某个字段缺失，或语言文件不存在时，AstrBot 会回退到默认文案：

- 插件名称、卡片短描述和描述回退到 `metadata.yaml` 中的 `display_name`、`short_desc`、`desc`。
- 配置项文案回退到 `_conf_schema.json` 中的 `description`、`hint`、`labels`。
- Page 文案回退到 Page 目录名、Page 默认标题或页面代码中提供的 fallback。

## 元数据

`metadata` 用于覆盖插件在插件页展示的名称、卡片短描述和描述。

```json
{
  "metadata": {
    "display_name": "天气助手",
    "short_desc": "一句话天气查询。",
    "desc": "查询天气并提供出行建议。"
  }
}
```

## 配置项

`config` 用于覆盖 `_conf_schema.json` 中的配置文案。结构按配置项名称嵌套。

例如 `_conf_schema.json`：

```json
{
  "enable": {
    "description": "Enable",
    "type": "bool",
    "hint": "Whether to enable this plugin.",
    "default": true
  },
  "mode": {
    "description": "Mode",
    "type": "string",
    "options": ["fast", "safe"],
    "labels": ["Fast", "Safe"]
  }
}
```

对应 `.astrbot-plugin/i18n/zh-CN.json`：

```json
{
  "config": {
    "enable": {
      "description": "启用",
      "hint": "是否启用这个插件。"
    },
    "mode": {
      "description": "模式",
      "labels": ["快速", "安全"]
    }
  }
}
```

`options` 是配置保存值，不建议翻译。下拉框的展示文本请使用 `labels`。

## 插件 Pages

`pages` 用于覆盖插件 Dashboard Page 的标题、描述和页面内自定义文案。结构按 Page 目录名嵌套。

例如插件页面目录：

```text
pages/
  settings/
    index.html
```

对应 `.astrbot-plugin/i18n/zh-CN.json`：

```json
{
  "pages": {
    "settings": {
      "title": "设置",
      "description": "管理这个插件的高级设置。",
      "save": "保存",
      "reset": "重置"
    }
  }
}
```

`title` 会用于 WebUI 外壳标题和插件详情页中的 Page 组件名称，`description` 会用于插件详情页中的 Page 组件描述。其他字段由页面通过 bridge 自行读取：

```js
const bridge = window.AstrBotPluginPage;

function render() {
  document.getElementById("save").textContent = bridge.t(
    "pages.settings.save",
    "Save",
  );
}

await bridge.ready();
render();
bridge.onContext(render);
```

`onContext()` 用于响应 WebUI 语言切换；监听后通常不需要刷新 Page。

## 嵌套配置

如果 `_conf_schema.json` 中有 `object` 类型配置，翻译也按同样的字段结构继续嵌套。

```json
{
  "config": {
    "sub_config": {
      "name": {
        "description": "名称",
        "hint": "显示在消息中的名称。"
      }
    }
  }
}
```

## 模板列表

`template_list` 的模板名称和模板内字段也可以翻译。模板名称放在 `templates.<模板名>.name`，模板内字段继续往下嵌套。

```json
{
  "config": {
    "rules": {
      "description": "规则",
      "templates": {
        "default": {
          "name": "默认模板",
          "threshold": {
            "description": "阈值",
            "hint": "达到该值后触发规则。"
          }
        }
      }
    }
  }
}
```

## 完整示例

下面是一个真实配置项的英文翻译示例：

```json
{
  "metadata": {
    "display_name": "HAPI Vibe Coding Remote",
    "desc": "Connect to a HAPI service and control coding agent sessions from chat platforms."
  },
  "config": {
    "hapi_endpoint": {
      "description": "HAPI service URL",
      "hint": "Example: http://localhost:3006"
    },
    "output_level": {
      "description": "SSE delivery level",
      "hint": "silence: permission requests only; simple: plain text messages and system events; summary: recent N messages when a task completes; detail: all messages in real time",
      "labels": ["Silence", "Simple", "Summary", "Detail"]
    }
  }
}
```

## 约束

插件国际化只读取 `.astrbot-plugin/i18n` 目录。语言文件必须使用嵌套 JSON 结构，不支持点号扁平 key。

## 指令名称与描述多语言

除了页面与配置文案，插件指令的**名称**和**描述**也支持多语言。

### 指令别名(多语言名称)

使用 `astrbot.api.star` 导出的 `multi_alias()` 为指令注册多语言别名：

```python
from astrbot.api.star import multi_alias

@filter.command(
    "weather",
    desc="获取天气",
    alias=multi_alias(zh="天气", ru="погода", jp="天気"),
)
async def weather(self, event, city: str): ...
```

- `/weather`、`/天气`、`/погода`、`/天気` 均会触发同一个 handler。
- **主命令(`/weather`)始终可用**，不受语言限制。
- 别名的语言范围由 WebUI「其他配置 → 全语言别名」开关决定：
  - **关闭(默认)**：仅**当前语言**对应的别名可用（如当前为 zh-CN 时 `/天气` 可用，`/погода` 不可用）；
  - **开启**：所有语言的别名均可用。
- 也可以直接传普通 `set`(旧写法 `alias={"天气"}`)，此时别名不带语言信息，
  视为全语言别名，不受「全语言别名」开关影响。

### 指令描述(多语言)

`@filter.command` 支持 `desc_i18n` 字段，按语言提供描述文字：

```python
@filter.command(
    "weather",
    desc="获取天气",  # 回退文案
    desc_i18n={
        "zh-CN": "获取天气",
        "en-US": "Get weather",
        "ru-RU": "Узнать погоду",
        "ja-JP": "天気を取得",
    },
)
async def weather(self, event, city: str): ...
```

描述取用顺序：`desc_i18n[当前语言]` → `desc`(原文) → 函数 docstring。
WebUI 的**指令管理页**与**插件详情页**会按 WebUI 界面语言显示描述。
(聊天内的内置 `/help` 只列内置指令,不含插件指令,故不显示插件描述。)

### 运行时获取当前语言(结果多语言)

插件如需按语言输出**回复结果**，使用 `get_lang()`：

```python
from astrbot.api.star import get_lang

@filter.command("weather")
async def weather(self, event, city: str):
    lang = await get_lang(self.context, event.unified_msg_origin)
    # lang: "zh-CN" | "en-US" | "ru-RU" | "ja-JP"
    text = LOCALE["sunny"].get(lang, LOCALE["sunny"]["en-US"])
    yield event.plain_result(text.format(city=city))
```

- `context.get_lang(umo)` 也可以直接在插件内使用，二者等价。
- 框架不翻译插件文案，插件自行维护翻译表；缺语言时建议回退到 `en-US` 或 `zh-CN`。
- 语言来源：**全局 `language` 配置**（`data/cmd_config.json`，默认 `zh-CN`）。

### 用户设置语言

语言是**全局配置**,所有会话统一使用;不支持按会话单独设置。
用户通过内置指令 `/lang` 查看或修改(内置指令名保持原有英文命名)：

```text
/lang           → 查看当前全局语言
/lang zh|en|ru|jp → 设置全局语言(仅管理员)
/lang reset     → 恢复默认语言 zh-CN(仅管理员)
```

管理员也可直接编辑 `data/cmd_config.json` 的 `language` 字段(默认 `zh-CN`)。
全局配置填错时按 `zh-CN` 生效，启动日志与 `/lang` 查看会给出提示。

> WebUI 里**指令名**按该全局配置显示（`multi_alias` 注册的对应语言别名）；
> 指令**描述**按 WebUI 界面语言显示。

## 兼容旧版 AstrBot

`multi_alias()` / `get_lang()` / `desc_i18n` 是较新版本才提供的能力。
若插件在这些能力发布前安装到旧版 AstrBot 上，`from astrbot.api.star import get_lang`
会抛出 `ImportError`，导致插件加载失败（仅该插件失败，不影响 AstrBot 与其他插件运行）。

建议二选一：

### 1. 声明所需的最低版本（推荐）

在 `metadata.yaml` 中声明 `astrbot_version`，AstrBot 会在加载前校验并给出明确提示：

```yaml
astrbot_version: ">=4.28.0"
```

### 2. 代码内降级（兼容新旧版本）

```python
try:
    from astrbot.api.star import get_lang, multi_alias
except ImportError:  # 旧版 AstrBot 没有这些 API

    async def get_lang(context, umo=None):
        return "zh-CN"  # 降级为固定语言

    def multi_alias(**langs):
        return set(langs.values())  # 降级:别名仍可用(不带语言信息)
```

这样插件在旧版上仍可加载，只是拿不到多语言效果。
