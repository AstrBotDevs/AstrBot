# 基于OpenAI ChatGPT的QQ频道机器人

## 功能：

### 基本功能
- @机器人可以获得回复
- 缓存每个用户与ChatGPT的会话
- 可在`configs/config.yaml`下配置`total_tokens_limit`来指定对每个用户的最大缓存tokens
> 关于token：token就相当于是AI中的单词数（但是不等于单词数），`text-davinci-003`模型中最大可以支持`4097`个token。在发送信息时，这个机器人会将用户的历史聊天记录打包发送给ChatGPT，因此，`token`也会相应的累加，为了保证聊天的上下文的逻辑性，就有了缓存token。
### 指令
需要先`@`机器人之后再输入指令
- 发送`/reset`重置prompt
- 发送`/his`查看历史记录（每个用户都有独立的会话）
- 发送`/his [页码数]`查看不同页码的历史记录。例如`/his 2`查看第2页
- 发送`/token`查看当前缓存的总token数

## 待实现功能：
- 将prompt持久化存储
- 更多交互方式
- ...

## 使用方法：
首先你需要获得
- OpenAI的key [OpenAI](https://beta.openai.com/)
- QQ开放平台下QQ频道机器人的token和appid [QQ开放平台](https://q.qq.com/)
- 一个QQ频道机器人（很容易创建~）

然后在configs/config.yaml下进行配置

然后启动main.py就行！
