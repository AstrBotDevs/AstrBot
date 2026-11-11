---
description: 注册、绑定、用量常见问题
icon: circle-question
---

# 常见问题

## 营业时间

<details>
<summary>鱼咖什么时候开门？关店米饭会不会没？</summary>

鱼咖 **非 24 小时营业**：早上 9 点到晚上 11 点（工作时间偶尔摸鱼）。关店时大肥鱼可能不回消息，但**你碗里的白饭额度一直留着不动**，开门接着吃。
</details>

## 注册与付款

<details>
<summary>没付款能先绑定吗？</summary>

不能。绑定与扫码入口仅在 **已开通套餐** 后显示。
</details>

<details>
<summary>付款了仍没有绑定入口？</summary>

刷新页面、重新登录；确认支付回调成功。仍不行则联系客服并提供支付单号。
</details>

## QQ 机器人

<details>
<summary>头像或名称改不了怎么办？</summary>

选好后若无法更改图片或名称，前往 [q.qq.com](https://q.qq.com) 处理（不是鱼咖用户中心）。[详细步骤](../qq-open-platform/avatar-name.md)
</details>

<details>
<summary>机器人不回复？</summary>

检查：是否完成绑定；开放平台 **IP 白名单**；沙箱是否包含你的 QQ/群；群内 **消息范围** 是否过窄；托管方实例是否运行中。
</details>

<details>
<summary>可以把教程里的扫码图发群里吗？</summary>

不要。微信绑定二维码应在 **你本人登录的用户中心** 内使用，避免他人绑到你的实例。QQ 走手填凭证，也不要把 AppSecret 发群。
</details>

<details>
<summary>QQ 为什么不扫鱼咖的码？</summary>

腾讯侧创建后还要绑 AI 服务。鱼咖对 QQ 用 **图文教学 + AppID/AppSecret**，直接接到大肥鱼，减少「未连接灵魂」。微信仍用扫码。
</details>

## 用量与费用

<details>
<summary>GitBook 上为什么看不到实时 Token？</summary>

教程是静态文档。**用量只在用户中心** 查看。[说明](../usage/dashboard.md)
</details>

<details>
<summary>服务系数是什么？</summary>

在模型成本上加收的托管服务费倍数，见 [费用如何计算](../usage/billing-coefficient.md)。
</details>

<details>
<summary>/cost 和用户中心数字不一致？</summary>

`/cost` 多为 **当前会话今日**；用户中心是 **你整条机器人实例** 的汇总。
</details>

## 记忆与隐私

<details>
<summary>我的聊天会被其他「鱼」看到吗？</summary>

不会。会话按机器人实例分开存储。详见 [什么是你的鱼](../persona/your-fish.md)。
</details>
