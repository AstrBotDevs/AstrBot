# 基于OpenAI ChatGPT的QQ频道机器人

## 功能：
- @机器人可以获得回复
- 以变量的形式临时保存了Session，具体原理为：将某一个用户id作为字典的key，value为历史prompt
- 发送`/reset`重置prompt
- 发送`/his`查看历史记录（每个用户都有独立的会话）

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
