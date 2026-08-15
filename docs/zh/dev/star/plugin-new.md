---
outline: deep
---

# AstrBot 插件开发指南

AstrBot 插件（Star）是加载到 AstrBot 进程中的 Python 包。插件应只依赖
`astrbot.api` 下公开的 SDK，不要从 `astrbot.core`、具体平台适配器或提供商实现中
导入内部对象。

## 环境准备

本仓库与插件均以 Python 3.14+ 为基线。先准备 AstrBot 源码工作区：

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
```

建议把插件作为独立 Git 仓库放在 AstrBot 工作区之外，并通过可编辑安装连接到
`data/plugins/`：

```bash
uv run astrbot plug install --editable ../astrbot_plugin_example
uv run main.py
```

可编辑安装会创建目录符号链接，修改插件源码后无需反复复制文件。Windows 用户可能
需要启用“开发人员模式”或以管理员身份创建该链接。

最小插件目录如下：

```text
astrbot_plugin_example/
  metadata.yaml
  main.py
  README.md
  requirements.txt  # 仅在有第三方依赖时需要
```

## 插件元数据

`metadata.yaml` 必须包含 `name`、`desc`、`version` 和 `author` 四个字段：

```yaml
name: astrbot_plugin_example
desc: 一个最小 AstrBot 插件
version: 0.1.0
author: Your Name
repo: https://github.com/your-org/astrbot_plugin_example
```

`name` 同时用于 Python 模块加载和插件安装目录，因此必须满足以下规则：

- 是合法的 Python 标识符，且不能是 `class`、`from` 等 Python 关键字；
- 不能包含斜杠、反斜杠、连字符、空格等不合法字符；
- 推荐使用全小写的 `astrbot_plugin_<名称>` 形式，并让仓库目录使用相同名称。

例如 `astrbot_plugin_weather` 合法，而 `astrbot-plugin-weather` 和
`astrbot/plugin/weather` 不合法。缺少任何必填字段或使用非法 `name` 时，插件会
被拒绝加载。

### 展示信息（可选）

`display_name` 是插件在 WebUI 和插件市场中显示的易读名称；`short_desc` 是卡片
上的单行短描述，缺省时回退到 `desc`：

```yaml
display_name: 示例插件
short_desc: 用一句话介绍插件。
```

名称和描述还可以随 WebUI 语言显示，详见
[插件国际化](./guides/plugin-i18n)。

### Logo（可选）

可以在插件根目录放置 `logo.png`。建议使用 1:1 比例和 256×256 像素。

![插件 logo 示例](https://files.astrbot.app/docs/source/images/plugin/plugin_logo.png)

### 声明支持平台（可选）

`support_platforms` 是平台适配器 ID 列表，WebUI 会展示该声明：

```yaml
support_platforms:
  - webchat
  - telegram
  - discord
```

当前可声明的 ID 包括：

- `aiocqhttp`
- `qq_official`
- `qq_official_webhook`
- `telegram`
- `wecom`
- `wecom_ai_bot`
- `lark`
- `dingtalk`
- `discord`
- `slack`
- `kook`
- `vocechat`
- `weixin_official_account`
- `weixin_oc`
- `satori`
- `misskey`
- `line`
- `matrix`
- `mattermost`
- `webchat`

该字段用于声明兼容范围，不会自动阻止处理其他平台的事件；需要运行时限制时，仍应
使用公开的事件过滤器。

### 声明 AstrBot 版本范围（可选）

`astrbot_version` 使用 PEP 440 版本约束，不要添加 `v` 前缀：

```yaml
astrbot_version: '>=4.26,<5'
```

当当前 AstrBot 版本不满足约束时，插件默认不会加载。WebUI 安装流程可以显式选择
忽略该警告，因此插件仍应在代码中避免依赖未声明的内部实现。

### 随插件提供 Skills（可选）

插件可以在根目录提供 `skills/`。AstrBot 会把其中合法的 Skill 注册为由该插件
管理的只读来源：

```text
astrbot_plugin_example/
  metadata.yaml
  main.py
  skills/
    web-search-helper/
      SKILL.md
    report-writer/
      SKILL.md
```

如果 `skills/` 本身就是一个 Skill，也可以直接放置 `skills/SKILL.md`。插件提供
的 Skill 可以在 WebUI 中启用或禁用，但不能作为本地 Skill 编辑或删除；插件更新
或卸载时，它们会随插件文件一起变化。

## 最小插件实现

`main.py` 中的插件类继承公开的 `Star`，构造函数接收按能力划分的
`PluginContext`：

```python
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import PluginContext, Star


class ExamplePlugin(Star):
    def __init__(self, context: PluginContext):
        super().__init__(context)

    async def initialize(self) -> None:
        """插件加载并激活后调用。"""
        logger.info("ExamplePlugin initialized")

    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        """回复一条问候消息。"""
        yield event.plain_result(f"Hello, {event.get_sender_name()}!")

    async def terminate(self) -> None:
        """插件停用、重载或 AstrBot 关闭时调用。"""
        logger.info("ExamplePlugin terminated")
```

`initialize()` 用于创建客户端、任务等运行时资源；`terminate()` 必须关闭这些资源，
例如取消后台任务、关闭 HTTP 客户端和释放文件句柄。不要使用已废弃的析构方法代替
显式生命周期清理。

## 插件日志

在 `Star` 实例方法中使用 `self.logger`，或在插件模块中使用
`from astrbot.api import logger`。两种方式都会路由到当前运行中插件的独立日志器。
在 Dashboard 的插件配置对话框中可选择该插件的日志级别，或选择“跟随全局”。设置会
立即生效并在重启后保留；选择“跟随全局”会清除插件自己的覆盖设置。

设计带参数、子指令或 option 的入口前，请阅读
[Orbit 指令设计规范](./guides/listen-message-event#orbit-指令设计规范)。该规范说明
指令头命名、确定性参数语法、支持的 handler 签名，以及 Telegram/Discord 原生指令
的兼容约束。

## 调试插件

插件修改后，在 WebUI 的插件管理页打开插件菜单并选择“重载插件”。如果插件加载
失败，先查看启动日志或管理页错误信息；修正代码后可以使用“一键重载修复”重新
加载。

处理函数中的前两个参数必须是 `self` 和 `event`。业务逻辑可以放在插件包的其他
模块中，但事件处理器本身需要注册在插件类上。

## 依赖与数据

插件有第三方依赖时，在插件根目录添加 `requirements.txt`。这些依赖必须支持
Python 3.14；不要为 Python 3.10–3.13 添加兼容分支。

持久化数据不要写入插件源码目录，否则更新或重装可能覆盖数据。使用
[插件存储](./guides/storage) 中的 `self.context.storage.data_directory()` 获取专属数据目录。

## 开发原则

- 为功能和回归问题编写测试。
- 只从 `astrbot.api` 使用公开插件接口。
- 对长生命周期任务、客户端和文件提供明确的终止与清理路径。
- 网络请求使用 `aiohttp` 或 `httpx` 等异步客户端，不要在事件循环中调用同步
  `requests`。
- 提交前使用 Ruff 格式化和检查 Python 代码。
- 扩展现有插件时，优先向原插件提交变更，除非它已停止维护。
- 如果插件直接借鉴其他项目的设计、功能创意或实现思路，请在 README 中清楚说明
  灵感来源，并附上相关项目链接。
- 如果使用、修改或移植其他项目的代码或资源，请遵守其开源许可证，并按许可证要求
  保留版权和许可声明。
