<div align="center">

<img src="https://socialify.git.ci/Soulter/QQChannelChatGPT/image?description=1&forks=1&issues=1&language=1&name=1&owner=1&pattern=Circuit%20Board&stargazers=1&theme=Light" alt="QQChannelChatGPT" width="600" height="300" />

<!-- [![Language](https://img.shields.io/badge/language-python-green.svg?style=plastic)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-AGPL3-orange.svg?style=plastic)](https://github.com/Soulter/QQChannelChatGPT/blob/master/LICENSE)
![Python](https://img.shields.io/badge/python-3.9+-blue) -->
 
基于go-cqhttp和官方QQ频道SDK的QQ机器人项目。支持ChatGPT、Claude、HuggingChat 大模型，集成插件功能。

部署文档：https://github.com/Soulter/AstrBot/wiki
 
欢迎加群讨论 | **QQ群号：322154837** | **频道号: x42d56aki2** |

<!-- <img src="https://user-images.githubusercontent.com/37870767/230417115-9dd3c9d5-6b6b-4928-8fe3-82f559208aab.JPG" width="300"></img> -->

</div>

## 🤔您可能想了解的
- **如何部署？** [帮助文档](https://github.com/Soulter/QQChannelChatGPT/wiki) (部署不成功欢迎进群捞人解决<3)
- **go-cqhttp启动不成功、报登录失败？** [在这里搜索解决方法](https://github.com/Mrs4s/go-cqhttp/issues)
- **程序闪退/机器人启动不成功？** [提交issue或加群反馈](https://github.com/Soulter/QQChannelChatGPT/issues)
- **如何开启ChatGPT、Bard、Claude等语言模型？** [查看帮助](https://github.com/Soulter/QQChannelChatGPT/wiki/%E8%A1%A5%E5%85%85%EF%BC%9A%E5%A6%82%E4%BD%95%E5%BC%80%E5%90%AFChatGPT%E3%80%81Bard%E3%80%81Claude%E7%AD%89%E8%AF%AD%E8%A8%80%E6%A8%A1%E5%9E%8B%EF%BC%9F)

## 🧩功能：

✨ 最近功能：
1. 支持切换代码分支。输入`/update checkout <分支名>`即可切换代码分支
2. 正在测试可视化面板，输入`/update checkout dev_dashboard`后根据提示即可体验

🌍支持的AI语言模型一览：

**文字模型/图片理解**

- OpenAI GPT-3模型（原生支持）
- OpenAI GPT-3.5模型（原生支持）
- OpenAI GPT-4模型（原生支持）
- ~~ChatGPT网页版 GPT-3.5模型（免费，原生支持）~~
- ~~ChatGPT网页版 GPT-4模型（需订阅Plus账户，原生支持）~~
- ~~Bing（免费，原生支持）~~
- Claude模型（免费，由[LLMs插件](https://github.com/Soulter/llms)支持）
- HuggingChat模型（免费，由[LLMs插件](https://github.com/Soulter/llms)支持）
- Google Bard（免费，由[LLMs插件](https://github.com/Soulter/llms)支持）

**图片生成**

- NovelAI/Naifu (免费，由[AIDraw插件](https://github.com/Soulter/aidraw)支持)


🌍机器人支持的能力一览：
- 同时部署机器人到 QQ 和 QQ 频道
- 大模型对话
- 大模型网页搜索能力 **(目前仅支持OpenAI系的模型，最新版本下使用 web on 指令打开)**
- 插件安装（在QQ或QQ频道聊天框内输入`plugin`了解详情）
- 回复文字图片渲染（以图片markdown格式回复，**大幅度降低被风控概率**，需手动在`cmd_config.json`内开启qq_pic_mode）
- 人格设置
- 关键词回复
- 热更新（更新本项目时**仅需**在QQ或QQ频道聊天框内输入`update latest r`）
- Windows一键部署（https://github.com/Soulter/QQChatGPTLauncher/releases/latest）

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

插件开发教程：https://github.com/Soulter/QQChannelChatGPT/wiki/%E5%9B%9B%E3%80%81%E5%BC%80%E5%8F%91%E6%8F%92%E4%BB%B6

部分插件：

- `LLMS`: https://github.com/Soulter/llms | Claude, HuggingChat 大语言模型接入。
 
- `GoodPlugins`: https://github.com/Soulter/goodplugins | 随机动漫图片、搜番、喜报生成器等等

- `sysstat`: https://github.com/Soulter/sysstatqcbot | 查看系统状态

- `BiliMonitor`: https://github.com/Soulter/BiliMonitor | 订阅B站动态
  
- `liferestart`: https://github.com/Soulter/liferestart | 人生重开模拟器

<img width="1231" alt="image" src="https://github.com/Soulter/AstrBot/assets/37870767/824d1ff3-7b85-481c-b795-8e62dedb9fd7">


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
- `/bing` 切换为bing
- `/revgpt` 切换为ChatGPT逆向库
- `/画` 画画

#### 逆向ChatGPT库语言模型
- `/gpt` 切换为OpenAI官方API
- `/bing` 切换为bing

* 切换模型指令支持临时回复。如`/bing 你好`将会临时使用一次bing模型 -->

## 📰使用方法：

使用文档：https://github.com/Soulter/QQChannelChatGPT/wiki

**Windows用户可以使用启动器一键安装，请前往Release下载最新版本（Beta）**
<!-- 
### 安装第三方库

```shell
pip install -r requirements.txt
```
> ⚠Python版本应>=3.9

### 配置

**详细部署教程链接：**https://github.com/Soulter/QQChannelChatGPT/wiki

### 启动
- 启动main.py -->

## 🙇‍感谢
本项目使用了一下项目:

[ChatGPT by acheong08](https://github.com/acheong08/ChatGPT)

[EdgeGPT by acheong08](https://github.com/acheong08/EdgeGPT)

[go-cqhttp by Mrs4s](https://github.com/Mrs4s/go-cqhttp)

[nakuru-project by Lxns-Network](https://github.com/Lxns-Network/nakuru-project)

<!-- ## 👀部分演示截图

帮助中心（`help`指令）
![)F%2VQA`O)`4BHTXZ653(~9](https://github.com/Soulter/QQChannelChatGPT/assets/37870767/57eaa8c6-6962-4940-823c-2e26b5206cf5)

 -->
## ⚙配置文件说明：
```yaml
# 如果你不知道怎么部署，请查看https://github.com/Soulter/QQChannelChatGPT/wiki
# 不一定需要key了，如果你没有key但有openAI账号或者必应账号，可以考虑使用下面的逆向库


###############平台设置#################

# QQ频道机器人
# QQ开放平台的appid和令牌
# q.qq.com
# enable为true则启用，false则不启用
qqbot:
  enable: true
  appid: 
  token: 

# QQ机器人
# enable为true则启用，false则不启用
# 需要安装GO-CQHTTP配合使用。
# 文档：https://docs.go-cqhttp.org/
# 请将go-cqhttp的配置文件的sever部分粘贴为以下内容，否则无法使用
# 请先启动go-cqhttp再启动本程序
# 
# servers:
#   - http:
#       host: 127.0.0.1
#       version: 0
#       port: 5700
#       timeout: 5
#   - ws:
#       address: 127.0.0.1:6700
#       middlewares:
#         <<: *default
gocqbot:
  enable: false

# 设置是否一个人一个会话
uniqueSessionMode: false
# QChannelBot 的版本，请勿修改此字段，否则可能产生一些bug
version: 3.0
# [Beta] 转储历史记录时间间隔(分钟)
dump_history_interval: 10
# 一个用户只能在time秒内发送count条消息
limit:
  time: 60
  count: 5
# 公告
notice: "此机器人由Github项目QQChannelChatGPT驱动。"
# 是否打开私信功能
# 设置为true则频道成员可以私聊机器人。
# 设置为false则频道成员不能私聊机器人。
direct_message_mode: true

# 系统代理
# http_proxy: http://localhost:7890
# https_proxy: http://localhost:7890

# 自定义回复前缀，如[Rev]或其他，务必加引号以防止不必要的bug。
reply_prefix:
  openai_official: "[GPT]"
  rev_chatgpt: "[Rev]"
  rev_edgegpt: "[RevBing]"

# 百度内容审核服务
# 新用户免费5万次调用。https://cloud.baidu.com/doc/ANTIPORN/index.html
baidu_aip:
  enable: false
  app_id: 
  api_key: 
  secret_key: 




###############语言模型设置#################


# OpenAI官方API
# 注意：已支持多key自动切换，方法：
# key:
#   - sk-xxxxxx
#   - sk-xxxxxx
# 在下方非注释的地方使用以上格式
# 关于api_base：可以使用一些云函数（如腾讯、阿里）来避免国内被墙的问题。
# 详见：
# https://github.com/Ice-Hazymoon/openai-scf-proxy
# https://github.com/Soulter/QQChannelChatGPT/issues/42
# 设置为none则表示使用官方默认api地址
openai:
  key: 
    - 
  api_base: none
  # 这里是GPT配置，语言模型默认使用gpt-3.5-turbo
  chatGPTConfigs:
    model: gpt-3.5-turbo
    max_tokens: 3000
    temperature: 0.9
    top_p: 1
    frequency_penalty: 0
    presence_penalty: 0
    
  total_tokens_limit: 5000

# 逆向文心一言【暂时不可用，请勿使用】
rev_ernie:
  enable: false

# 逆向New Bing
# 需要在项目根目录下创建cookies.json并粘贴cookies进去。
# 详见：https://soulter.top/posts/qpdg.html
rev_edgegpt:
  enable: false

# 逆向ChatGPT库
# https://github.com/acheong08/ChatGPT
# 优点：免费（无免费额度限制）；
# 缺点：速度相对慢。OpenAI 速率限制：免费帐户每小时 50 个请求。您可以通过多帐户循环来绕过它
# enable设置为true后，将会停止使用上面正常的官方API调用而使用本逆向项目
#
# 多账户可以保证每个请求都能得到及时的回复。
# 关于account的格式
# account:
#   - email: 第1个账户
#     password: 第1个账户密码
#   - email: 第2个账户
#     password: 第2个账户密码
#   - ....
# 支持使用access_token登录
# 例：
# - session_token: xxxxx
# - access_token: xxxx
# 请严格按照上面这个格式填写。
# 逆向ChatGPT库的email-password登录方式不工作，建议使用access_token登录
# 获取access_token的方法，详见：https://soulter.top/posts/qpdg.html
rev_ChatGPT:
  enable: false
  account:
    - access_token: 
```
