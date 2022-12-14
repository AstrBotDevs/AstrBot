# 基于OpenAI ChatGPT的QQ频道机器人

## ⭐体验
扫码加入QQ频道

<img src="screenshots/5.jpg" width = "200"/>

**机器人已上线，可以把↑频道内的ChatGPTBot机器人拉到自己频道去了~**

↓ **演示截图**在文档最后 ↓

欢迎Star本项目

## ⭐功能：

### 基本功能
- 可以在频道内@或者私信机器人
- 缓存每个用户与ChatGPT的会话
- 可在`configs/config.yaml`下配置`total_tokens_limit`来指定对每个用户的最大缓存tokens
- 统计频道、会话、消息数量
> 关于token：token就相当于是AI中的单词数（但是不等于单词数），`text-davinci-003`模型中最大可以支持`4097`个token。在发送信息时，这个机器人会将用户的历史聊天记录打包发送给ChatGPT，因此，`token`也会相应的累加，为了保证聊天的上下文的逻辑性，就有了缓存token。
### 指令功能
需要先`@`机器人之后再输入指令
- `/reset`重置prompt
- `/his`查看历史记录（每个用户都有独立的会话）
- `/his [页码数]`查看不同页码的历史记录。例如`/his 2`查看第2页
- `/token`查看当前缓存的总token数
- `/count` 查看统计
- `/status` 查看chatGPT的配置

## 📰使用方法：

### 安装第三方库

使用Python的pip工具安装
- `qq-botpy` （QQ频道官方Python SDK）
- `openai` (OpenAI 库)

> ⚠注意，由于qq-botpy需要运行在`Python 3.8+`的版本上，因此本项目也需要在此之上运行

### 配置

- 获得 OpenAI的key [OpenAI](https://beta.openai.com/)
- 获得 QQ开放平台下QQ频道机器人的token和appid [QQ开放平台](https://q.qq.com/)，一个QQ频道机器人（很容易创建~）
- 在configs/config.yaml下进行配置

### 启动
- 启动main.py

## DEMO
![1.jpg](screenshots/1.jpg)
![3.jpg](screenshots/3.jpg)
![2.jpg](screenshots/2.jpg)
