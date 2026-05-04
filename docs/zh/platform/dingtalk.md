# 接入钉钉 DingTalk

## 支持的基本消息类型

> 版本 v4.15.0。

| 消息类型 | 是否支持接收 | 是否支持发送 | 备注 |
| --- | --- | --- | --- |
| 文本 | 是 | 是 | |
| 图片 | 是 | 是 | |
| 语音 | 否 | 是 | |
| 视频 | 否 | 是 | |
| 文件 | 否 | 是 | |

主动消息推送：支持。

## 创建和配置应用

前往 [钉钉开放平台](https://open-dev.dingtalk.com/fe/app)，点击创建应用：

![image](https://files.astrbot.app/docs/source/images/dingtalk/image-4.png)

创建好之后，添加应用能力，选择机器人：

![image](https://files.astrbot.app/docs/source/images/dingtalk/image-5.png)

点击机器人配置，填写填写机器人相关信息：

![image](https://files.astrbot.app/docs/source/images/dingtalk/image-7.png)

确认无误后，点击下面的发布按钮。

点击凭证与基础信息，将 `ClientID` 和 `ClientSecret` 复制下来。

## 开始连接

打开 AstrBot 管理面板 -> `机器人` -> `+ 创建机器人`，创建一个钉钉适配器。

将刚刚复制的 `ClientID` 和 `ClientSecret` 填入，点击保存，AstrBot 将会自动向钉钉开放平台请求。

回到钉钉开放平台，点击事件订阅，选择 `Stream 模式推送`，点击保存，如果没有意外情况，将会看到 连接接入成功 字样。

![image](https://files.astrbot.app/docs/source/images/dingtalk/image-8.png)

点击保存即可。

## 发布版本

点击边栏的 版本管理与发布，创建一个新版本。

填写应用版本号、版本描述、应用可见范围（选择全部员工或者按照您的需求），点击保存，确认发布。

![alt text](https://files.astrbot.app/docs/source/images/dingtalk/image-11.png)

找到一个钉钉群聊，点击右上角的设置：

![image](https://files.astrbot.app/docs/source/images/dingtalk/image-12.png)

下拉找到添加机器人，然后找到刚刚创建的机器人，点击添加即可：

![image](https://files.astrbot.app/docs/source/images/dingtalk/image-9.png)

## 🎉 大功告成

在群聊中 @ 机器人后附带 `/help` 指令，如果机器人回复了，那么说明接入成功。
