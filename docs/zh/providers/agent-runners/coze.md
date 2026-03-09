# 接入 Coze

AstrBot v4.2.1 之后的版本, 支持接入 [Coze](https://www.coze.cn/) 的 Agent 服务。

## 预备工作：准备 API Key

首先我们注册并登录 [Coze](https://www.coze.cn/) 账号，然后进入 [API Key 管理页面](https://www.coze.cn/open/oauth/pats) 创建一个新的 API Key。

你可以按图片的步骤到达 API Key 管理页面， 也可以点击上面的链接直接进入。

![创建 API Key](https://files.astrbot.app/docs/source/images/coze/image_1.png)

随后, 点击 "创建", 在下面的页面填写你的 API Key 名称, 选择一个过期时间(不建议使用永久令牌), 在 "权限" 处选择点击 "全选", 选择一个工作空间, 然后点击 "确定"。

![创建令牌](https://files.astrbot.app/docs/source/images/coze/image_2.png)

随后我们可以得到一个新的 API Key, 请复制保存好, 后面会用到。

![新的 API Key](https://files.astrbot.app/docs/source/images/coze/image_3.png)

## 预备工作: 配置智能体

进入 [项目开发](https://www.coze.cn/space/develop) 页面, 点击右上角 "+项目" 创建一个新的项目, 选择创建智能体。

![新建项目](https://files.astrbot.app/docs/source/images/coze/image_4.png)

![新建项目](https://files.astrbot.app/docs/source/images/coze/image_5.png)

**注意**: 完成智能体创建后, 必须先点击右上角的发布 **发布** 智能体, 并在发布中的 "选择发布平台" 处将 API 分栏全部勾选上, 然后点击 "发布"。

> 如果没有发布或发布时没有勾选 API 分栏, 则无法通过 API 调用智能体。

![发布智能体](https://files.astrbot.app/docs/source/images/coze/image_6.png)

点击发布后, 智能体就创建完成了, 你可以在智能体开发页面的发布按钮左侧看到发布历史记录, 以确认智能体已经发布成功。

接下来注意在智能体开发页面的链接:

![智能体开发](https://files.astrbot.app/docs/source/images/coze/image_7.png)

例如示例中链接为: "https://www.coze.cn/space/7553214941005004863/bot/7553248674860826660"

那么 `bot_id` 就是链接中 `bot/` 后面的那一串数字: `7553248674860826660`

我们需要将 `bot_id` 记录下来, 后面会用到。

## 在 AstrBot 中配置 Coze

完成了所有预备工作, 现在我们就可以在 AstrBot 中配置 Coze 了。

进入 AstrBot 管理面板 -> 服务提供商 -> 新增服务提供商 -> Coze, 进入配置页面。

![Coze 供应商](https://files.astrbot.app/docs/source/images/coze/image_8.png)

填入刚刚创建的 API Key 和 bot_id, 然后点击保存。

> 其他配置说明:
>
> - API Base URL: 一般不需要修改, 如果你使用的是 Coze 国际版, 这里修改为: "https://api.coze.com"
> - 由 Coze 管理对话记录: 如描述所示。

## 选择 Agent 执行器

进入左边栏配置页面，点击「Agent 执行方式」，选择「Coze」，然后在下方出现的新的配置项中选择你刚刚创建的 Coze Agent 执行器的 ID，点击右下角「保存」，即可完成配置。
