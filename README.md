# 基于OpenAI ChatGPT的QQ频道机器人🤖

## ⭐体验
欢迎添加QQ：905617992

或者扫码直接加入QQ频道

<img src="screenshots/5.jpg" width = "200"/>

↓ **演示截图**在文档最后 ↓
欢迎Star本项目⭐

## ⭐功能：

### ✨基本功能
- @机器人、私信都可以获得回复
- 缓存每个用户与ChatGPT的会话
- 可在`configs/config.yaml`下配置`total_tokens_limit`来指定对每个用户的最大缓存tokens
> 关于token：token就相当于是AI中的单词数（但是不等于单词数），`text-davinci-003`模型中最大可以支持`4097`个token。在发送信息时，这个机器人会将用户的历史聊天记录打包发送给ChatGPT，因此，`token`也会相应的累加，为了保证聊天的上下文的逻辑性，就有了缓存token。
### 💻指令
需要先`@`机器人之后再输入指令
- 发送`/reset`重置prompt
- 发送`/his`查看历史记录（每个用户都有独立的会话）
- 发送`/his [页码数]`查看不同页码的历史记录。例如`/his 2`查看第2页
- 发送`/token`查看当前缓存的总token数

## 待实现功能：
- 更多交互方式
- ...

## 📰使用方法：

### 安装第三方库

使用Python的pip工具安装
- `qq-botpy` （QQ频道官方Python SDK）
- `openai` (OpenAI 库)

> ⚠注意，由于qq-botpy需要运行在`Python 3.8+`的版本上，因此本项目也需要在此之上运行

### 配置各种Key

首先你需要获得

- OpenAI的key [OpenAI](https://beta.openai.com/)
- QQ开放平台下QQ频道机器人的token和appid [QQ开放平台](https://q.qq.com/)
- 一个QQ频道机器人（很容易创建~）

然后在configs/config.yaml下进行配置

然后启动main.py就行！

## DEMO
![1.jpg](screenshots/1.jpg)
![3.jpg](screenshots/3.jpg)
![2.jpg](screenshots/2.jpg)
