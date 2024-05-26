<p align="center">

<img src="https://github.com/Soulter/AstrBot/assets/37870767/b1686114-f3aa-4963-b07f-28bf83dc0a10" alt="QQChannelChatGPT" width="200" />
</p>
<div align="center">

# AstrBot

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/Soulter/AstrBot)](https://github.com/Soulter/AstrBot/releases/latest)
<img src="https://wakatime.com/badge/user/915e5316-99c6-4563-a483-ef186cf000c9/project/34412545-2e37-400f-bedc-42348713ac1f.svg" alt="wakatime">
<img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="python">
<a href="https://hub.docker.com/r/soulter/astrbot"><img alt="Docker pull" src="https://img.shields.io/docker/pulls/soulter/astrbot.svg"/></a>
<a href="https://qm.qq.com/cgi-bin/qm/qr?k=EYGsuUTfe00_iOu9JTXS7_TEpMkXOvwv&jump_from=webapi&authKey=uUEMKCROfsseS+8IzqPjzV3y1tzy4AkykwTib2jNkOFdzezF9s9XknqnIaf3CDft">
<img alt="Static Badge" src="https://img.shields.io/badge/QQ群-322154837-purple">
</a>
<img alt="Static Badge" src="https://img.shields.io/badge/频道-x42d56aki2-purple">

<a href="https://astrbot.soulter.top/center">项目部署</a> ｜
<a href="https://github.com/Soulter/QQChannelChatGPT/issues">问题提交</a> ｜
<a href="https://astrbot.soulter.top/center/docs/%E5%BC%80%E5%8F%91/%E6%8F%92%E4%BB%B6%E5%BC%80%E5%8F%91">插件开发（最少只需 25 行）</a>
</div>

## 🤔您可能想了解的
- **如何部署？** [帮助文档](https://astrbot.soulter.top/center/docs/%E9%83%A8%E7%BD%B2/%E9%80%9A%E8%BF%87Docker%E9%83%A8%E7%BD%B2) (部署不成功欢迎进群捞人解决<3)
- **go-cqhttp启动不成功、报登录失败？** [在这里搜索解决方法](https://github.com/Mrs4s/go-cqhttp/issues)
- **程序闪退/机器人启动不成功？** [提交issue或加群反馈](https://github.com/Soulter/QQChannelChatGPT/issues)
- **如何开启 ChatGPT、Claude、HuggingChat 等语言模型？** [查看帮助](https://astrbot.soulter.top/center/docs/%E4%BD%BF%E7%94%A8/%E5%A4%A7%E8%AF%AD%E8%A8%80%E6%A8%A1%E5%9E%8B)

## 🧩功能：

✨ 最近功能：
1. 可视化面板
2. Docker 一键部署项目：[链接](https://astrbot.soulter.top/center/docs/%E9%83%A8%E7%BD%B2/%E9%80%9A%E8%BF%87Docker%E9%83%A8%E7%BD%B2)

🌍支持的消息平台/接口
- go-cqhttp（QQ、QQ频道）
- QQ 官方机器人接口
- Telegram（由 [astrbot_plugin_telegram](https://github.com/Soulter/astrbot_plugin_telegram) 插件支持）

🌍支持的AI语言模型一览：

**文字模型/图片理解**

- OpenAI GPT-3（原生支持）
- OpenAI GPT-3.5（原生支持）
- OpenAI GPT-4（原生支持）
- Claude（免费，由[LLMs插件](https://github.com/Soulter/llms)支持）
- HuggingChat（免费，由[LLMs插件](https://github.com/Soulter/llms)支持）
- Gemini（免费，由[LLMs插件](https://github.com/Soulter/llms)支持）

**图片生成**
- OpenAI Dalle 接口
- NovelAI/Naifu (免费，由[AIDraw插件](https://github.com/Soulter/aidraw)支持)

🌍机器人支持的能力一览：
- 可视化面板（beta）
- 同时部署机器人到 QQ 和 QQ 频道
- 大模型对话
- 大模型网页搜索能力 **(目前仅支持OpenAI系模型，最新版本下使用 web on 指令打开)**
- 插件（在QQ或QQ频道聊天框内输入 `plugin` 了解详情）
- 回复文字图片渲染（以图片markdown格式回复，**大幅度降低被风控概率**，需手动在`cmd_config.json`内开启qq_pic_mode）
- 人格设置
- 关键词回复
- 热更新（更新本项目时**仅需**在QQ或QQ频道聊天框内输入`update latest r`）
- Windows一键部署 https://github.com/Soulter/QQChatGPTLauncher/releases/latest

<!-- 
### 基本功能
<details> 
 <summary>✅ 回复符合上下文</summary>

   -  程序向API发送近多次对话内容，模型根据上下文生成回复

   -  你可在`configs/config.yaml`中修改`total_token_limit`来近似控制缓存大小。
 </details> 

<details> 
 <summary>✅ 超额自动切换</summary>

   -  超额时，程序自动切换openai的key，方便快捷
   
</details>

<details> 

 <summary>✅ 支持统计频道、消息数量等信息</summary> 

   -  实现了简单的统计功能

 </details>

<details> 
 <summary>✅ 多并发处理，回复速度快</summary> 
  
   -  使用了协程，理论最高可以支持每个子频道每秒回复5条信息
  
 </details>

<details>
 <summary>✅ 持久化转储历史记录，重启不丢失</summary> 

   -  使用内置的sqlite数据库存储历史记录到本地

   -  方式为定时转储，可在`config.yaml`下修改`dump_history_interval`来修改间隔时间，单位为分钟。
  
 </details>

<details> 
 <summary>✅ 支持多种指令控制</summary> 
  
   -  详见下方`指令功能`
  
 </details>

<details>
<summary>✅ 官方API，稳定</summary>

   -  不使用ChatGPT逆向接口，而使用官方API接口，稳定方便。

   -  QQ频道机器人框架为QQ官方开源的框架，稳定。

</details> -->

<!-- > 关于token：token就相当于是AI中的单词数（但是不等于单词数），`text-davinci-003`模型中最大可以支持`4097`个token。在发送信息时，这个机器人会将用户的历史聊天记录打包发送给ChatGPT，因此，`token`也会相应的累加，为了保证聊天的上下文的逻辑性，就有了缓存token。 -->

### 🛠️ 插件支持

本项目支持接入插件。

> 使用`plugin i 插件GitHub链接`即可安装。

部分插件：

- `LLMS`: https://github.com/Soulter/llms | Claude, HuggingChat 大语言模型接入。
 
- `GoodPlugins`: https://github.com/Soulter/goodplugins | 随机动漫图片、搜番、喜报生成器等。

- `sysstat`: https://github.com/Soulter/sysstatqcbot | 查看系统状态

- `BiliMonitor`: https://github.com/Soulter/BiliMonitor | 订阅B站动态
  
- `liferestart`: https://github.com/Soulter/liferestart | 人生重开模拟器

- `astrbot_plugin_aiocqhttp`: https://github.com/Soulter/astrbot_plugin_aiocqhttp | aiocqhttp 适配器，支持接入支持反向 WS 的 OneBot 协议实现，如 Lagrange.OneBot，Shamrock 等。


<img width="900" alt="image" src="https://github.com/Soulter/AstrBot/assets/37870767/824d1ff3-7b85-481c-b795-8e62dedb9fd7">


<!-- 
### 指令

#### OpenAI官方API
在频道内需要先`@`机器人之后再输入指令；在QQ中暂时需要在消息前加上`ai `，不需要@
- `/reset`重置prompt
- `/his`查看历史记录（每个用户都有独立的会话）
- `/his [页码数]`查看不同页码的历史记录。例如`/his 2`查看第2页
- `/token`查看当前缓存的总token数
- `/count` 查看统计
- `/status` 查看chatGPT的配置
- `/help` 查看帮助
- `/key` 动态添加key
- `/set` 人格设置面板
- `/keyword nihao 你好` 设置关键词回复。nihao->你好
- `/画` 画画

#### 逆向ChatGPT库语言模型
- `/gpt` 切换为OpenAI官方API

* 切换模型指令支持临时回复。如`/a 你好`将会临时使用一次bing模型 -->
<!--
## 🙇‍感谢

本项目使用了一下项目:

[ChatGPT by acheong08](https://github.com/acheong08/ChatGPT)

[EdgeGPT by acheong08](https://github.com/acheong08/EdgeGPT)

[go-cqhttp by Mrs4s](https://github.com/Mrs4s/go-cqhttp)

[nakuru-project by Lxns-Network](https://github.com/Lxns-Network/nakuru-project) -->
