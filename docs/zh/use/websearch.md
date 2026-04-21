# 网页搜索

网页搜索功能旨在为大模型提供联网检索能力，以获取最近信息，一定程度上能够提高回复准确度，减少幻觉。

AstrBot 内置的网页搜索功能依赖大模型提供 `函数调用` 能力。如果你不了解函数调用，请参考：[函数调用](/use/websearch)。

在使用支持函数调用的大模型且开启了网页搜索功能的情况下，你可以试着说：

- `帮我搜索一下 xxx`
- `帮我总结一下这个链接：https://soulter.top`
- `查一下 xxx`
- `最近 xxxx`

等等带有搜索意味的提示，让大模型触发调用搜索工具。

AstrBot 当前支持 5 种网页搜索源接入方式：`Tavily`、`BoCha`、`百度 AI 搜索`、`Brave`、`Exa`。

![image](https://files.astrbot.app/docs/source/images/websearch/image.png)

进入 `配置`，下拉找到网页搜索，你可选择 `Tavily`、`BoCha`、`百度 AI 搜索`、`Brave` 或 `Exa`。

### Tavily

前往 [Tavily](https://app.tavily.com/home) 获取 API Key，然后填写在相应的配置项。

### BoCha

前往 BoCha 平台获取 API Key，然后填写在相应的配置项。

### 百度 AI 搜索

前往百度千帆 APP Builder 获取 API Key，然后填写在相应的配置项。

### Brave

前往 Brave Search 获取 API Key，然后填写在相应的配置项。

### Exa

前往 [Exa](https://dashboard.exa.ai) 获取 API Key，然后填写在相应的配置项。

如果你使用 Tavily 作为网页搜索源，在 AstrBot ChatUI 上会获得更好的体验优化，包括引用来源展示等：

![](https://files.astrbot.app/docs/source/images/websearch/image1.png)
