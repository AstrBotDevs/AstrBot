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

README 也可以按语言提供 Markdown 文件。AstrBot 会先读取完整 locale，再读取短语言，最后回退到 `README.md`：

```text
README.md
README_zh-CN.md
README_zh.md
README.zh.md
README_en-US.md
README_en.md
```

`README_<locale>.md`、`README-<locale>.md` 和 `README.<locale>.md` 均可识别，文件名大小写不敏感。如果没有默认 README，但插件只提供一个本地化 README，AstrBot 会显示该文件。市场中的未安装 GitHub 插件会按同样的顺序读取默认分支中的 README；非 GitHub 仓库需要插件源提供 `readme_url`。

当当前语言没有对应翻译、某个字段缺失，或语言文件不存在时，AstrBot 会回退到默认文案：

- 插件名称、卡片短描述和描述回退到 `metadata.yaml` 中的 `display_name`、`short_desc`、`desc`。
- 配置项文案回退到 `_conf_schema.json` 中的 `description`、`hint`、`labels`、`subtitles`。
- Page 文案回退到 Page 目录名、Page 默认标题或页面代码中提供的 fallback。

## 元数据

`metadata` 用于覆盖插件在插件页展示的名称、卡片短描述和描述。

侧栏的插件分组标题、悬浮提示和使用插件名称的默认标题也会读取当前语言的 `metadata.display_name`，切换语言后立即更新。侧栏只接受非空字符串；翻译缺失、为空白或类型无效时，依次回退到原始 `display_name`、`name`。已有 `views.<视图名>.title` 优先于 `pages.<视图名>.title` 的解析规则不变；分组内没有有效标题的视图仍显示目录名。路由、置顶和展开状态使用稳定的插件 ID 或视图路径，不随名称翻译变化。

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
    "labels": ["Fast", "Safe"],
    "subtitles": ["Faster responses", "More conservative processing"]
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
      "labels": ["快速", "安全"],
      "subtitles": ["更快响应", "更保守的处理"]
    }
  }
}
```

`options` 是配置保存值，不建议翻译。下拉框的展示文本请使用 `labels`。 `subtitles` 用于选项下方的说明，并与 `options` 按索引对应。

## 插件可视化视图

`views` 用于覆盖插件 Dashboard 可视化视图的标题、描述和视图内自定义文案（`pages` 是其别名，保持兼容）。结构按视图目录名嵌套。

例如插件可视化视图目录：

```text
views/
  settings/
    index.html
```

对应 `.astrbot-plugin/i18n/zh-CN.json`：

```json
{
  "views": {
    "settings": {
      "title": "设置",
      "description": "管理这个插件的高级设置。",
      "save": "保存",
      "reset": "重置"
    }
  }
}
```

`title` 会用于侧边栏、WebUI 外壳标题和插件详情页中的视图组件名称，`description` 会用于插件详情页中的视图组件描述。其他字段由页面通过 bridge 自行读取：

```js
const bridge = window.AstrBotPluginView;

function render() {
  document.getElementById("save").textContent = bridge.t(
    "views.settings.save",
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
