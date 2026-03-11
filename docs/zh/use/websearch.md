# 网页搜索

网页搜索功能旨在提供大模型调用 Google，Bing，搜狗等搜索引擎以获取世界最近信息的能力，一定程度上能够提高大模型的回复准确度，减少幻觉。

AstrBot 内置的网页搜索功能依赖大模型提供 `函数调用` 能力。如果你不了解函数调用，请参考：[函数调用](/use/websearch)。

在使用支持函数调用的大模型且开启了网页搜索功能的情况下，您可以试着说：

- `帮我搜索一下 xxx`
- `帮我总结一下这个链接：https://soulter.top`
- `查一下 xxx`
- `最近 xxxx`

等等带有搜索意味的提示让大模型触发调用搜索工具。

AstrBot 支持 3 种网页搜索源接入方式：`默认`、`Tavily`、`百度 AI 搜索`。

前者使用 AstrBot 内置的网页搜索请求器请求 Google、Bing、搜狗搜索引擎，在能够使用 Google 的网络环境下表现最佳。**我们推荐使用 Tavily**。

![image](https://files.astrbot.app/docs/source/images/websearch/image.png)

进入 `配置`，下拉找到网页搜索，您可选择 `default`（默认，不推荐） 或 `Tavily`。

### default（不推荐）

如果您的设备在国内并且有代理，可以开启代理并在 `管理面板-其他配置-HTTP代理` 填入 HTTP 代理地址以应用代理。

### Tavily

前往 [Tavily](https://app.tavily.com/home) 得到 API Key，然后填写在相应的配置项。

如果您使用 Tavily 作为网页搜索源，在 AstrBot ChatUI 上将会获得更好的体验优化，包括引用来源展示等：

![](https://files.astrbot.app/docs/source/images/websearch/image1.png)