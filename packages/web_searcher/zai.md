# 联网搜索

<Info>
  智谱AI 为开发者提供全系列 AI 搜索工具，覆盖 **基础检索（Web Search API）**、**问答增强（Web Search in Chat）**、**搜索智能体（Search Agent）** 三大服务，基于统一 API 接口集成自研引擎及第三方服务（搜狗/夸克），提供从原始网页数据抓取、搜索结果与 LLM 生成融合、到多轮对话上下文管理的全链路能力，助力开发者以 **更低成本** 构建可信、实时、可溯源的 AI 应用。
</Info>

* 查看 [产品价格](https://bigmodel.cn/pricing)
* 查看您的 [API Key](https://open.bigmodel.cn/usercenter/apikeys)

## 服务概览

<CardGroup cols={3}>
  <Card title="Web Search API" icon={<svg style={{maskImage: "url(/resource/icon/book.svg)", WebkitMaskImage: "url(/resource/icon/book.svg)", maskRepeat: "no-repeat", maskPosition: "center center",}} className={"h-6 w-6 bg-primary dark:bg-primary-light !m-0 shrink-0"} />}>
    直接获取**结构化搜索结果**（标题/摘要/链接等），支持多搜索引擎
  </Card>

  <Card title="Web Search in Chat" icon={<svg style={{maskImage: "url(/resource/icon/comments.svg)", WebkitMaskImage: "url(/resource/icon/comments.svg)", maskRepeat: "no-repeat", maskPosition: "center center",}} className={"h-6 w-6 bg-primary dark:bg-primary-light !m-0 shrink-0"} />}>
    将搜索结果融入大模型生成**回答并标注网页结果来源**，实时检索+LLM生成无缝衔接
  </Card>

  <Card title="Search Agent" icon={<svg style={{maskImage: "url(/resource/icon/headset.svg)", WebkitMaskImage: "url(/resource/icon/headset.svg)", maskRepeat: "no-repeat", maskPosition: "center center",}} className={"h-6 w-6 bg-primary dark:bg-primary-light !m-0 shrink-0"} />}>
    根据搜索意图进行**query拆解**，对话状态管理与智能路由，意图理解增强上下文管理
  </Card>
</CardGroup>

## Web Search API

Web Search API 是一个专给大模型用的搜索引擎，在传统搜索引擎网页抓取、排序的能力基础上，增强了意图识别能力，返回更适合大模型处理的结果（网页标题、网页 URL、网页摘要、网站名称、网站图标等）。

1. **意图增强检索**：支持智能识别用户查询意图，自动判断是否需要网页检索
2. **结构化输出**：返回适合 LLM 处理的数据格式（含标题/URL/摘要/网站名/图标等）
3. **多引擎支持**：整合智谱自研引擎及主流搜索引擎（搜狗/夸克）
4. **支持指定范围搜索**：可自定义返回的搜索结果数量、域名、时间范围等指定搜索，并可调整网页摘要的字数，帮助实现搜索行为的精细化管控
5. **可灵活控制输出结果时间**：响应参数可设置网页发布时间字段，便于时效性分析和排序

**接口调用**

* 接口文档：[Web Search API](/api-reference/%E5%B7%A5%E5%85%B7-api/%E7%BD%91%E7%BB%9C%E6%90%9C%E7%B4%A2)
* 场景示例：搜索财经新闻

<Tabs>
  <Tab title="Python">
    **安装 SDK**

    ```bash
    # 安装最新版本
    pip install zai-sdk

    # 或指定版本
    pip install zai-sdk==0.0.3.3
    ```

    **验证安装**

    ```python
    import zai
    print(zai.__version__)
    ```

    ```python
    from zai import ZhipuAiClient

    client = ZhipuAiClient(api_key="your-api-key")

    response = client.web_search.web_search(
       search_engine="search_pro",
       search_query="搜索2025年4月的财经新闻",
       count=15,  # 返回结果的条数，范围1-50，默认10
       search_domain_filter="www.sohu.com",  # 只访问指定域名的内容
       search_recency_filter="noLimit",  # 搜索指定日期范围内的内容
       content_size="high"  # 控制网页摘要的字数，默认medium
    )
    print(response)
    ```
  </Tab>

  <Tab title="Java">
    **安装 SDK**

    **Maven**

    ```xml
    <dependency>
        <groupId>ai.z.openapi</groupId>
        <artifactId>zai-sdk</artifactId>
        <version>0.0.4</version>
    </dependency>
    ```

    **Gradle (Groovy)**

    ```groovy
    implementation 'ai.z.openapi:zai-sdk:0.0.4'
    ```

    ```java
    import ai.z.openapi.ZhipuAiClient;
    import ai.z.openapi.service.web_search.WebSearchService;
    import ai.z.openapi.service.web_search.WebSearchRequest;
    import ai.z.openapi.service.web_search.WebSearchResponse;

    public static void main(String[] args) {

        ZhipuAiClient client = ZhipuAiClient.builder().build();;
        WebSearchService webSearchService = client.webSearch();

        WebSearchRequest request = WebSearchRequest.builder()
            .searchEngine("search_pro")
            .searchQuery("搜索2025年4月的财经新闻")
            .count(15)  // 返回结果的条数，范围1-50，默认10
            .searchDomainFilter("www.sohu.com")  // 只访问指定域名的内容
            .searchRecencyFilter("noLimit")  // 搜索指定日期范围内的内容
            .contentSize("high")  // 控制网页摘要的字数，默认medium
            .build();

        WebSearchResponse response = webSearchService.createWebSearch(request);
        System.out.println(response);
    }
    ```
  </Tab>

  <Tab title="响应示例">
    ```json
    WebSearchResp(
    {
        "created": 1748261757,
        "id": "20250526201557dda85ca6801b467b",
        "request_id": "20250526201557dda85ca6801b467b",
        "search_intent": [
            {
                "intent": "SEARCH_ALL",
                "keywords": "2025年4月 财经新闻",
                "query": "搜索2025年4月的财经新闻"
            }
        ],
        "search_result": [
            {
                "content": "一、1-4月我国对外直接投资575.4亿美元，同比增长7.5%。以旧换新成效持续显现，家电类商品零售额连续8个月保持两位数增长。",
                "icon": "https://sfile.chatglm.cn/searchImage/sohu_icon_new.jpg",
                "link": "https://www.sohu.com/a/897879632_121123890",
                "media": "搜狐",
                "publish_date": "2025-05-23",
                "refer": "ref_1",
                "title": "2025年5月23日财经早资讯"
            }
        ]
    }
    )
    ```
  </Tab>
</Tabs>

### MCP Server

访问[官方MCP文档](https://modelcontextprotocol.io/introduction)了解更多关于该协议的信息。

<Accordion title="MCP Server 配置指南">
  **安装指南**

  * 使用支持MCP协议的客户端，如Cursor和Cherry Studio。
  * 从智谱AI 平台获取 [API 密钥](https://open.bigmodel.cn/usercenter/apikeys)。

  **在Cursor中使用**

  Cursor 0.45.6包含MCP功能。Cursor 作为 MCP 服务客户端，可以通过简单配置连接到 MCP 服务。

  导航路径：Cursor设置 → \[功能] → \[MCP服务器]

  **配置 MCP 服务器**

  ```json
  {
    "mcpServers": {
      "zhipu-web-search-sse": {
        "url": "https://open.bigmodel.cn/api/mcp-broker/proxy/web-search/mcp?Authorization=Your Zhipu API Key"
      }
    } 
  }
  ```

  **Cursor MCP 使用方法**

  Cursor MCP 需在 Composer 的 Agent 模式下使用。
</Accordion>

## 对话中的网络搜索

对话中的网络搜索允许 Completions API 调用搜索引擎，将实时网络检索结果与 GLM 的生成能力相结合，提供最新且可验证的答案。

* API文档：[对话中的网络搜索](/api-reference/%E6%A8%A1%E5%9E%8B-api/%E5%AF%B9%E8%AF%9D%E8%A1%A5%E5%85%A8)
* 示例：财经分析摘要

<Tabs>
  <Tab title="Python">
    **安装 SDK**

    ```bash
    # 安装最新版本
    pip install zai-sdk

    # 或指定版本
    pip install zai-sdk==0.0.3.3
    ```

    **验证安装**

    ```python
    import zai
    print(zai.__version__)
    ```

    ```python
    from zai import ZhipuAiClient

    client = ZhipuAiClient(api_key="your-api-key")

    # 定义工具参数
    tools = [{
        "type": "web_search",
        "web_search": {
            "enable": "True",
            "search_engine": "search_pro",
            "search_result": "True",
            "search_prompt": "你是一位财经分析师。请用简洁的语言总结网络搜索{search_result}中的关键信息，按重要性排序并引用来源日期。今天的日期是2025年4月11日。",
            "count": "5",
            "search_domain_filter": "www.sohu.com",
            "search_recency_filter": "noLimit",
            "content_size": "high"
        }
    }]

    # 定义用户消息
    messages = [{
        "role": "user",
        "content": "2025年4月的重要财经事件、政策变化和市场数据"
    }]

    # 调用API获取响应
    response = client.chat.completions.create(
        model="glm-4-air",  # 模型标识符
        messages=messages,  # 用户消息
        tools=tools         # 工具参数
    )

    # 打印响应结果
    print(response)
    ```
  </Tab>

  <Tab title="Java">
    **安装 SDK**

    **Maven**

    ```xml
    <dependency>
        <groupId>ai.z.openapi</groupId>
        <artifactId>zai-sdk</artifactId>
        <version>0.0.4</version>
    </dependency>
    ```

    **Gradle (Groovy)**

    ```groovy
    implementation 'ai.z.openapi:zai-sdk:0.0.4'
    ```

    ```java
    import ai.z.openapi.ZhipuAiClient;
    import ai.z.openapi.service.chat.ChatService;
    import ai.z.openapi.service.model.ChatCompletionCreateParams;
    import ai.z.openapi.service.model.ChatCompletionResponse;
    import ai.z.openapi.service.model.ChatMessage;
    import ai.z.openapi.service.model.ChatMessageRole;
    import ai.z.openapi.service.model.ChatTool;
    import ai.z.openapi.service.model.ChatToolType;
    import ai.z.openapi.service.model.WebSearch;

    import java.util.ArrayList;
    import java.util.List;

    public static void main(String[] args) {
      // 创建客户端
      ZhipuAiClient client = ZhipuAiClient.builder().build();;
      ChatService chatService = client.chat();

      // 定义用户消息
      List<ChatMessage> messages = new ArrayList<>();
      ChatMessage userMessage = new ChatMessage(ChatMessageRole.USER.value(),
      "2025年4月的重要财经事件、政策变化和市场数据");
      messages.add(userMessage);

      // 定义工具参数
      List<ChatTool> tools = new ArrayList<>();
      ChatTool webSearchTool = new ChatTool();
      webSearchTool.setType(ChatToolType.WEB_SEARCH.value());

      WebSearch webSearch = WebSearch.builder()
      .enable(true)
      .searchEngine("search_pro")
      .searchResult(true)
      .searchPrompt("你是一位财经分析师。请用简洁的语言总结网络搜索{search_result}中的关键信息，按重要性排序并引用来源日期。今天的日期是2025年4月11日。")
      .count(5)
      .searchDomainFilter("www.sohu.com")
      .searchRecencyFilter("noLimit")
      .contentSize("high")
      .build();

      webSearchTool.setWebSearch(webSearch);
      tools.add(webSearchTool);

      // 调用API获取响应
      ChatCompletionCreateParams request = ChatCompletionCreateParams.builder()
      .model("glm-4-air")  // 模型标识符
      .messages(messages)  // 用户消息
      .tools(tools)        // 工具参数
      .toolChoice("auto")  // 自动选择工具
      .stream(false)       // 非流式响应
      .build();

      ChatCompletionResponse response = chatService.createChatCompletion(request);

      // 打印响应结果
      System.out.println(response);
    }

    ```
  </Tab>

  <Tab title="响应示例">
    ```json
    {
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "message": {
                    "content": "根据您提供的文档，以下是2025年4月的重要财经事件，按重要性排序：\n\n1. **G20财长和央行行长会议** - 日期待定。G20会议将讨论全球经济复苏、金融稳定和可持续发展等关键议题。这将对全球经济政策协调和金融市场情绪产生深远影响。[来源：ref_1]\n\n2. **多国和地区制造业PMI初值发布** - 包括法国、德国、欧元区和英国。这些数据将揭示各自制造业部门的活动状况，为投资者提供关键洞察。[来源：ref_1]",
                    "role": "assistant"
                }
            }
        ],
        "created": 1748311718,
        "id": "20250527100811da2f8f7243f94b02",
        "model": "glm-4-air",
        "request_id": "20250527100811da2f8f7243f94b02",
        "usage": {
            "completion_tokens": 868,
            "prompt_tokens": 4199,
            "total_tokens": 5067
        }
    }
    ```
  </Tab>
</Tabs>

## 搜索引擎说明

| **搜索引擎编码**             | **特性**                                 | **价格**  |
| :--------------------- | :------------------------------------- | :------ |
| **search\_std**        | 基础版（智谱AI 自研）：满足日常查询需求，性价比极高            | 0.01元/次 |
| **search\_pro**        | 高级版（智谱AI 自研）：多引擎协作显著降低空结果率，召回率和准确率大幅提升 | 0.03元/次 |
| **search\_pro\_sogou** | 搜狗：覆盖腾讯生态（新闻/企鹅号）和知乎内容，在百科、医疗等垂直领域权威性强 | 0.05元/次 |
| **search\_pro\_quark** | 夸克：精准触达垂直内容                            | 0.05元/次 |
