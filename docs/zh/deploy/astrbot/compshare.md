# 通过优云智算部署

优云智算是 UCloud 旗下的 GPU 算力租赁和大模型 API 调用平台，致力于为 AI、深度学习、科学计算相关客户提供丰富多样的算力资源。

AstrBot 在优云智算发布了 Ollama + AstrBot 一键自部署镜像，并且接入了优云智算 LLM API。

## 使用 Ollama + AstrBot 一键自部署镜像

> 镜像默认参数为：RTX 3090 24GB + Intel 16核 + 64GB RAM + 200GB 系统盘。采用按量付费的方式，请留意您的余额使用情况。

1. 通过 [此链接](https://passport.compshare.cn/register?referral_code=FV7DcGowN4hB5UuXKgpE74) 注册优云智算账户。
1. 打开 [AstrBot 镜像链接](https://www.compshare.cn/images/0oX7xoGrzfre)，点击创建实例。
2. 部署成功后，在[控制台](https://console.compshare.cn/light-gpu/console/resources)中打开「JupyterLab」
3. 进入JupyterLab后，新建一个终端 Terminal，在终端中粘贴以下指令

```bash
cd
./astrbot_booter.sh
```

指令运行结果如下所示即说明启动成功。

```txt
(py312) root@f8396035c96d:/workspace# cd
./astrbot_booter.sh
Starting AstrBot...
Starting ollama...
Both services started in the background.
```

启动成功后，在浏览器中输入 `http://实例的外网IP:6185` 即可访问 AstrBot 的界面。外网 IP 可以在 控制台->基础网络（外网）中获取。

> 可能需要等待半分钟左右。

首次登录时请使用启动日志内的随机初始密码（用户名通常是 astrbot），登录后请立即修改密码。

登录成功后，可以重新设置密码，并进入 AstrBot 的页面。

实例默认会导入 Ollama-DeepSeek-R1-32B 模型。

## 使用其他模型

### 使用 Ollama 拉取模型

镜像原生部署了 Ollama，您可以通过 Ollama 指令自行拉取想要的模型，将模型本地部署在实例。

1. 在 [Ollama](https://ollama.com/search) 模型列表找到想部署的模型。
2. 通过 SSH 进入到实例的终端（进入优云智算平台的控制台页面->实例列表->控制台指令和密码）
3. 通过 `ollama pull 模型名` 拉取模型，等待拉取成功。
4. 在 `模型提供商 → 对话` 中选择镜像预配置的 Ollama 提供商源，点击 `获取模型列表`，在刚拉取的模型旁点击 `+` 添加。如果没有预配置的源，点击 `新增`，选择 `Ollama`，填写实例中的 Ollama 地址后点击 `保存并获取模型`。

### 使用优云智算提供的模型 API

AstrBot 支持接入优云智算提供的模型 API。

1. 在 [优云智算](https://console.compshare.cn/light-gpu/model-center) 找到想要接入的模型
2. 打开 `模型提供商 → 对话 → 新增`，选择 `OpenAI Compatible`，填写优云智算的 API Key，并将 API Base URL 设为 `https://api.modelverse.cn/v1`。
3. 点击 `保存并获取模型`，在需要的模型旁点击 `+`。如果接口未返回模型列表，先 `保存配置`，再点击 `自定义模型`，填写平台提供的完整模型 ID。

### 测试

在已配置的模型上点击 `测试模型`，确认连接成功。然后进入 `配置文件`，选择机器人使用的配置文件，在 `AI → 模型 → 对话模型` 中选择刚添加的模型，点击 `保存配置`。

通过 WebUI 顶部的聊天切换按钮进入聊天，或直接向已接入消息平台的机器人发送消息，测试实际回复。

## 接入到消息平台

- 飞书：[接入到飞书](https://docs.astrbot.app/platform/lark.html)
- LINE：[接入到 LINE](https://docs.astrbot.app/platform/line.html)
- 钉钉：[接入到钉钉](https://docs.astrbot.app/platform/dingtalk.html)
- 企业微信：[接入到企业微信应用](https://docs.astrbot.app/platform/wecom.html)
- 微信客服：[接入到微信客服](https://docs.astrbot.app/platform/wecom.html)
- 微信公众平台：[接入到微信公众平台](https://docs.astrbot.app/platform/weixin-official-account.html)
- QQ 官方机器人平台：[接入到 QQ 机器人](https://docs.astrbot.app/platform/qqofficial/webhook.html)
- KOOK：[接入到 KOOK](https://docs.astrbot.app/platform/kook.html)
- Slack：[接入到 Slack](https://docs.astrbot.app/platform/slack.html)
- Discord：[接入到 Discord](https://docs.astrbot.app/platform/discord.html)
- 更多接入方式参考 [AstrBot 官方文档](https://docs.astrbot.app/what-is-astrbot.html)

## 更多功能

更多功能请参考 [AstrBot 官方文档](https://docs.astrbot.app)。
