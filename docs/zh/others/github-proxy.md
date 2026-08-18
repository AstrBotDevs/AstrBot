# GitHub 镜像

当前 fork **默认不提供** GitHub 镜像列表，Dashboard 也不再接受任意自定义镜像输入。

插件安装、插件更新和 Core 更新只会请求：

- GitHub 官方相关域名；
- 当前仍使用的 Soulter 上游兼容源（`api.soulter.top`、`astrbot-registry.soulter.top`）；
- 通过后端校验的公开 HTTPS origin。

如果 API 传入镜像前缀，它必须是：

- 明确的 HTTPS origin；
- 不含用户名/密码；
- 解析结果全部为公网地址；
- 不能重定向到未校验的内部地址。

这不是普通 HTTP 正向代理。功能语义是“URL 前缀镜像”，每一跳都会重新校验。插件 `download_url` 即使来自已登录的安装权限，也会拒绝私网和非 HTTPS。
