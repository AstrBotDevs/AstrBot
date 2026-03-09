
# Web Search

The web search feature aims to provide large language models with the ability to invoke search engines like Google, Bing, and Sogou to obtain recent world information, which can improve the accuracy of model responses and reduce hallucinations to some extent.

AstrBot's built-in web search functionality relies on the large language model's `function calling` capability. If you're not familiar with function calling, please refer to: [Function Calling](/use/websearch).

When using a large language model that supports function calling with the web search feature enabled, you can try saying:

- `Help me search for xxx`
- `Help me summarize this link: https://soulter.top`
- `Look up xxx`
- `Recent xxxx`

And other prompts with search intent to trigger the model to invoke the search tool.

AstrBot supports 3 types of web search source integration: `default`, `Tavily`, and `Baidu AI Search`.

The former uses AstrBot's built-in web search requester to query Google, Bing, and Sogou search engines, performing best in network environments with Google access. **We recommend using Tavily**.

![image](https://files.astrbot.app/docs/source/images/websearch/image.png)

Go to `Configuration`, scroll down to find Web Search, where you can select `default` (default, not recommended) or `Tavily`.

### default (Not Recommended)

If your device is in China and you have a proxy, you can enable the proxy and enter the HTTP proxy address in `Admin Panel - Other Configuration - HTTP Proxy` to apply the proxy.

### Tavily

Go to [Tavily](https://app.tavily.com/home) to get an API Key, then fill it in the corresponding configuration item.

If you use Tavily as your web search source, you will get a better experience optimization on AstrBot ChatUI, including citation source display and more:

![](https://files.astrbot.app/docs/source/images/websearch/image1.png)
