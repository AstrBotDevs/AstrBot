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
