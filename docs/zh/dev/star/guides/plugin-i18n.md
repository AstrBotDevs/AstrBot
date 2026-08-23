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

AstrBot 仅支持 `zh-CN.json` 和 `en-US.json`。文件内容必须是 JSON object。

当当前语言没有对应翻译、某个字段缺失，或语言文件不存在时，AstrBot 会回退到默认文案：

- 插件名称、卡片短描述和描述回退到 `metadata.yaml` 中的 `display_name`、`short_desc`、`desc`。
- 配置项文案回退到 `_conf_schema.json` 中的 `description` 和 `hint`。

## 元数据

`metadata` 用于覆盖插件列表中的名称、卡片短描述和描述。

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
      "description": "模式"
    }
  }
}
```

`options` 是配置保存值，不应翻译。当前 i18n 解析器只稳定返回字符串，不能翻译 `labels` 数组；下拉框的 `labels` 请直接放在 `_conf_schema.json`，或暂时保持与保存值相同。

## 指令回复

`commands` 用于运行时指令回复。通过 `context.i18n.t(event, message_key, **kwargs)` 读取，locale 顺序为 `event` extra `locale`、会话 preference `locale`，然后默认 `zh-CN`。缺键先回退 `en-US`，再回退到 key 本身。

```json
{
  "commands": {
    "variable.set.ok": "已为当前会话存储 {key}。使用 /variable unset 移除。"
  }
}
```

```python
text = await self.context.i18n.t(event, "variable.set.ok", key=key)
```

Python 源码不要写死用户可见中英混排。指令 handler 回复后应 `stop_event()`。

## 插件 Dashboard Pages

插件 Dashboard Pages（插件在 `pages/` 目录下提供的自定义 Web UI 页面）的标题和描述也可以通过 `pages` 字段翻译，按页面名称嵌套：

```json
{
  "pages": {
    "overview": {
      "title": "总览",
      "description": "查看插件的运行状态和统计信息。"
    }
  }
}
```

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
      "hint": "silence: permission requests only; simple: plain text messages and system events; summary: recent N messages when a task completes; detail: all messages in real time"
    }
  }
}
```

## 约束

插件国际化只读取 `.astrbot-plugin/i18n` 目录。语言文件必须使用嵌套 JSON object，不支持点号扁平 key。只有 `zh-CN`、`en-US` 两种 locale；其他 locale，或单个文件超过 1 MiB、文件名 locale 为空或超过 32 个字符、JSON 无效或顶层不是 object 时，运行时会跳过该文件。

翻译叶子值应使用字符串。数组和对象不是当前 WebUI 的稳定翻译值；尤其不要在 locale 文件中覆盖 `labels` 数组。
