# 网页搜索

网页搜索功能旨在为大模型提供联网检索能力，以获取最近信息，一定程度上能够提高回复准确度，减少幻觉。

AstrBot 内置的网页搜索功能依赖大模型提供 `函数调用` 能力。如果你不了解函数调用，请参考：[函数调用](/use/function-calling)。

在使用支持函数调用的大模型且开启了网页搜索功能的情况下，您可以试着说：

- `帮我搜索一下 xxx`
- `帮我总结一下这个链接：https://github.com/Xero-Team/AstrBot`
- `查一下 xxx`
- `最近 xxxx`

等等带有搜索意味的提示让大模型触发调用搜索工具。

AstrBot 当前支持 7 种网页搜索源接入方式：`Tavily`、`BoCha`、`百度 AI 搜索`、`Brave`、`Firecrawl`、`Exa`、`AnySearch`。

![image](https://files.astrbot.app/docs/source/images/websearch/image.png)

进入 `配置`，下拉找到网页搜索，您可选择 `Tavily`、`BoCha`、`百度 AI 搜索`、`Brave`、`Firecrawl`、`Exa` 或 `AnySearch`。

## Tavily

前往 [Tavily](https://app.tavily.com/home) 得到 API Key，然后填写在相应的配置项。

## BoCha

前往 BoCha 平台获取 API Key，然后填写在相应的配置项。

## 百度 AI 搜索

前往百度千帆 APP Builder 获取 API Key，然后填写在相应的配置项。

## Brave

前往 Brave Search 获取 API Key，然后填写在相应的配置项。

## Firecrawl

前往 [Firecrawl](https://firecrawl.dev) 获取 API Key，然后填写在相应的配置项。

## Exa

前往 [Exa](https://dashboard.exa.ai) 获取 API Key，然后填写在相应的配置项。Exa 是一个 AI 原生搜索引擎，支持关键词和语义搜索，提供分类过滤、域名限制和日期范围等高级搜索功能。

如果您使用 Tavily 作为网页搜索源，在 AstrBot ChatUI 上将会获得更好的体验优化，包括引用来源展示等：

![](https://files.astrbot.app/docs/source/images/websearch/image1.png)

## AnySearch

前往 [AnySearch 控制台](https://anysearch.com/console/api-keys) 获取 API Key，然后填写在相应的配置项。

AnySearch 除通用网页搜索外，还提供学术、代码文档、金融、法律、安全情报等垂直领域检索能力。若 API Key 留空，将以匿名模式调用，每日有免费额度，便于快速试用。
