---
outline: deep
---

# AstrBot 插件开发指南 🌠

欢迎来到 AstrBot 插件开发指南！本章节将引导您如何开发 AstrBot 插件。在我们开始之前，希望你能具备以下基础知识：

1. 有一定的 Python 编程经验。
2. 有一定的 Git、GitHub 使用经验。

欢迎加入我们的开发者专用 QQ 群: `975206796`。

## 环境准备

### 获取插件模板

1. 打开 AstrBot 插件模板: [helloworld](https://github.com/Soulter/helloworld)
2. 点击右上角的 `Use this template`
3. 然后点击 `Create new repository`。
4. 在 `Repository name` 处填写您的插件名。插件名格式:
   - 推荐以 `astrbot_plugin_` 开头；
   - 不能包含空格；
   - 保持全部字母小写；
   - 尽量简短。
5. 点击右下角的 `Create repository`。

### 克隆项目到本地

克隆 AstrBot 项目本体和刚刚创建的插件仓库到本地。

```bash
git clone https://github.com/AstrBotDevs/AstrBot
mkdir -p AstrBot/data/plugins
cd AstrBot/data/plugins
git clone 插件仓库地址
```

然后，使用 `VSCode` 打开 `AstrBot` 项目。找到 `data/plugins/<你的插件名字>` 目录。

更新 `metadata.yaml` 文件，填写插件的元数据信息。

> [!WARNING]
> 请务必修改此文件，AstrBot 识别插件元数据依赖于 `metadata.yaml` 文件。

### 设置插件 Logo（可选）

可以在插件目录下添加 `logo.png` 文件作为插件的 Logo。请保持长宽比为 1:1，推荐尺寸为 256x256。

![插件 logo 示例](https://files.astrbot.app/docs/source/images/plugin/plugin_logo.png)

### 插件展示名（可选）

可以修改(或添加) `metadata.yaml` 文件中的 `display_name` 字段，作为插件在插件市场等场景中的展示名，以方便用户阅读。

插件展示名和描述支持按 WebUI 语言显示，详见[插件国际化](./guides/plugin-i18n)。

### 插件短描述（可选）

你可以在 `metadata.yaml` 中新增 `short_desc` 字段，作为插件市场卡片上的短描述。它适合写成一句简短介绍；如果没有提供，卡片会回退显示 `desc`。

```yaml
short_desc: 一句话介绍你的插件。
```

### 随插件提供 Skills（可选）

插件可以在自己的目录下提供 `skills/` 文件夹。AstrBot 加载插件后会自动把其中合法的 Skill 纳入 Skill Manager，来源会显示为对应插件。

推荐一个插件包含多个 Skill 时使用以下结构：

```text
your_plugin/
  metadata.yaml
  main.py
  skills/
    web-search-helper/
      SKILL.md
    report-writer/
      SKILL.md
```

如果 `skills/` 本身就是一个 Skill，也可以直接放置：

```text
your_plugin/
  skills/
    SKILL.md
```

这种情况下 Skill 名称会使用插件目录名。插件提供的 Skill 由插件管理，在 WebUI 的 `插件 → 技能` 页面中作为只读来源展示；可以启用或禁用，但不能从本地 Skills 页面删除或编辑。插件卸载或更新后，对应 Skill 会随插件文件变化。

### 声明支持平台（Optional）

你可以在 `metadata.yaml` 中新增 `support_platforms` 字段（`list[str]`），声明插件支持的平台适配器。WebUI 插件页会展示该字段。

```yaml
support_platforms:
  - telegram
  - discord
```

`support_platforms` 中的值需要使用 `ADAPTER_NAME_2_TYPE` 的 key，目前支持：

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

### 声明 AstrBot 版本范围（Optional）

你可以在 `metadata.yaml` 中新增 `astrbot_version` 字段，声明插件要求的 AstrBot 版本范围。格式与 `pyproject.toml` 依赖版本约束一致（PEP 440），且不要加 `v` 前缀。

```yaml
astrbot_version: ">=4.16,<5"
```

可选示例：

- `>=4.17.0`
- `>=4.16,<5`
- `~=4.17`

如果你只想声明最低版本，可以直接写：

- `>=4.17.0`

当当前 AstrBot 版本不满足该范围时，插件会被阻止加载并提示版本不兼容。
在 WebUI 安装插件时，你可以选择“无视警告，继续安装”来跳过这个检查。

### 调试插件

AstrBot 采用在运行时注入插件的机制。因此，在调试插件时，需要启动 AstrBot 本体。

您可以使用 AstrBot 的热重载功能简化开发流程。

插件的代码修改后，在 AstrBot WebUI 的 `插件` 页找到自己的插件，点击插件卡片上的刷新图标（`重载插件`）。

如果插件因为代码错误等原因加载失败，可以在同一页面的 `加载失败插件` 列表中点击对应插件的 `重载` 按钮。

### 热重载的边界

重载会先调用插件的 `terminate()`，然后重新导入代码，并且只重新导入**插件目录内**的模块。记住这两条边界，可以少踩两个坑：「点了重载却没生效」和「重载后同一段逻辑跑了两份」。

**插件目录内的代码会重新执行。** 重载时，AstrBot 先卸载 `sys.modules` 中所有以 `data.plugins.<插件目录>` 为前缀的模块（日志中可以看到 `Removed module data.plugins.<插件目录>.main from plugin <插件目录>`），再重新导入。因此 `main.py`、插件目录下的子包、`skills/` 都是点重载即生效。

**插件目录之外的模块不会被重新导入，改完需要重启 AstrBot 进程。** 常见情况：

- 在插件里往 `sys.path` 追加了自定义路径，再 import 了插件目录之外的自有包；
- 在本地修改或替换了插件所依赖的第三方库；
- 与其他插件共用的、位于 `data/` 或其他位置的公共代码。

使用 `astrbot run --reload`（`-r`）时的自动重载同样只监听插件目录，插件目录之外的文件改动不会触发重载。

排查「重载了但代码没变」时，先确认模块实际是从哪个文件加载的：

```python
import your_shared_module

logger.info(your_shared_module.__file__)
```

如果打印出的路径不在 `data/plugins/<你的插件目录>/` 下，它就不在重载范围内。

**资源清理由 `terminate()` 负责。** 重载会调用一次 `terminate()`，所以你在插件里发起的后台任务（`asyncio.create_task`、`aiohttp.ClientSession`、线程、定时器）都应当在这里取消或关闭。否则每重载一次就会多出一份仍在运行的旧实例，表现为同一条消息被回复多次。`__del__` 是已废弃的旧钩子，与 `terminate` 同时实现时只有 `__del__` 会被调用，清理逻辑请只写在 `terminate` 里。

改完 `_conf_schema.json` 也需要重载插件，WebUI 才会读到新的配置项。

### 插件依赖管理

目前 AstrBot 对插件的依赖管理使用 `pip` 自带的 `requirements.txt` 文件。如果你的插件需要依赖第三方库，请务必在插件目录下创建 `requirements.txt` 文件并写入所使用的依赖库，以防止用户在安装你的插件时出现依赖未找到(Module Not Found)的问题。

> `requirements.txt` 的完整格式可以参考 [pip 官方文档](https://pip.pypa.io/en/stable/reference/requirements-file-format/)。

## 开发原则

感谢您为 AstrBot 生态做出贡献，开发插件请遵守以下原则，这也是良好的编程习惯。

- 功能需经过测试。
- 需包含良好的注释。
- 持久化数据请存储于 `data` 目录下，而非插件自身目录，防止更新/重装插件时数据被覆盖。
- 良好的错误处理机制，不要让插件因一个错误而崩溃。
- 在进行提交前，请使用 [ruff](https://docs.astral.sh/ruff/) 工具格式化您的代码。
- 不要使用 `requests` 库来进行网络请求，可以使用 `aiohttp`, `httpx` 等异步网络请求库。
- 如果是对某个插件进行功能扩增，请优先给那个插件提交 PR 而不是单独再写一个插件（除非原插件作者已经停止维护）。
- 如果直接借鉴了其他项目的设计、功能创意或实现思路，请在 README 中清楚说明灵感来源并附上相关项目链接。
- 如果使用、修改或移植了其他项目的代码或资源，请遵守原项目的开源许可协议，并按协议要求保留版权及许可声明。
