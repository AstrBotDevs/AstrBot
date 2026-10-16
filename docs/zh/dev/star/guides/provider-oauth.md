# 通过插件为 AI 供应商实现 OAuth 登录

插件可以注册 AI 供应商并实现登录，不必把供应商写进 AstrBot 核心。`astrbot.api.provider.oauth` 提供 `OAuth2Session`、`OAuth2Token` 和 `OAuth2Error`。供应商端点、客户端注册、权限范围、登录界面与凭据存储由插件管理。

目前支持**公共客户端的授权码流程、PKCE S256 和刷新令牌**。不包含设备授权、客户端密钥、OIDC 身份验证、供应商私有协议或自动回调服务。网站登录成功不代表令牌能够调用模型：供应商必须允许你的注册客户端，并在 AI API 上接受取得的 Bearer 令牌。

## 完整示例

仓库的 `examples/astrbot_plugin_oauth_provider/` 包含配置结构、插件元数据、加密存储和[插件页面](./plugin-pages.md)。示例复用 AstrBot 的 OpenAI 兼容适配器，处理模型列表、普通对话和流式对话，不预置某一家供应商。

1. 向支持 PKCE 与 OpenAI 兼容推理接口的供应商注册公共 OAuth 客户端，取得授权端点、令牌端点、客户端 ID、允许的 scopes、已登记的回调 URI 和 API base。不要从其他应用复制私有客户端 ID。
2. 在 AstrBot 使用的 Python 环境中生成存储加密密钥：

   ```sh
   python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   ```

   通过进程环境变量或部署密钥，将结果设为 `ASTRBOT_OAUTH_STORAGE_KEY`。重启时保持不变，与数据库分开备份。不要写进插件配置、Git 仓库或浏览器存储。密钥丢失后需要重新登录。
3. 将示例目录复制到 AstrBot 数据目录下的 `data/plugins/astrbot_plugin_oauth_provider/` 对应位置。在 WebUI 配置插件，再重载。缺少环境密钥或 OAuth 设置时，首次加载会明确失败，不会注册不可用的供应商。
4. 从插件详情打开 `oauth` 页面，点击 **Start sign-in**，复制授权地址到浏览器并授权。将跳转后的**完整 URL** 粘贴回来，点击 **Complete sign-in**。必须由发起登录的同一 Dashboard 用户在十分钟内完成。
5. 在供应商界面添加 **Plugin OAuth Example** 并选择模型。不用填写 API Key，凭据来自插件。请求地址由插件的 `api_base` 固定，不接受模型级覆盖。热重载后，可在插件页点击 **Activate saved models** 重建已有模型实例，或重启 AstrBot。正常启动已经在插件之后加载供应商，因此插件不会重复加载模型。

示例**不启动本地回调监听器**。使用示例回调 `http://127.0.0.1:14567/callback` 时，授权后的页面可能显示连接失败，直接复制地址栏中的完整 URL 即可。供应商必须允许该精确回调地址。强制自动回调的供应商需要单独实现、审查回调接入，不要为此取消 Dashboard 插件接口的鉴权。远程访问 Dashboard 时应使用 HTTPS。

示例的全部模型共用**一个供应商账号**。私有 KV 键包含供应商、客户端配置与 scopes，修改配置不会把旧凭据静默发往新 API。旧配置命名空间会保留；需要删除当前账号凭据时，应先断开连接再修改配置。

## 插件接口

```python
from astrbot.api.provider import (
    register_provider_adapter,
    unregister_provider_adapter,
)
from astrbot.api.provider.oauth import OAuth2Error, OAuth2Session, OAuth2Token
```

每个账号创建一个 `OAuth2Session`，传入明确、可信的端点，以及异步 `load_token()`、`save_token(token)` 回调。同一账号的所有模型共享该 session，避免并发刷新冲突。只共享存储键、却创建多个 session 或运行多个进程，不能协调令牌轮换。`save_token(None)` 必须删除凭据，持久化应保持原子性。核心接口不会自动加密存储；示例通过外部密钥，用 Fernet 加密插件私有 KV 中的值。

`begin_authorization(owner=...)` 返回授权地址。owner 应取自 `astrbot.api.web.request.username`，不能信任请求体中的用户名。向 `complete_authorization(...)` 传入完整回调 URL 和同一认证用户。`cancel_authorization(owner=...)` 仅取消待完成登录，不会断开已连接账号。新尝试会替换旧尝试；关闭页面后，未完成尝试会自行过期。

基于 HTTPX 的供应商，应将请求钩子加到**推理客户端**，不能加到令牌交换客户端：

```python
client.event_hooks["request"].append(session.authorize_request)
client.follow_redirects = False
```

示例通过现有 `_create_http_client` 扩展点接入。钩子在 SDK 准备请求后附加最新 Bearer 令牌，覆盖模型列表和流式请求，不修改共享 SDK 客户端的 API Key 字段。目标超出配置的 API 源与路径时，在读取凭据前拒绝请求。该客户端只用于推理，不要复用它下载任意图片或文件。

其他传输方式可以在服务端使用 `await session.get_access_token()`，但必须自行检查目标地址与重定向。不要把此方法包装成浏览器可读取令牌的接口。

## 生命周期与失败处理

服务器提供过期时间时，令牌会在到期前刷新。并发调用共用一次刷新，新刷新令牌持久化后才使用。重新登录不会继承旧账号的刷新令牌。`invalid_grant` 会清除本地授权；暂时性故障不会清除已存账号。持久化失败时停止使用凭据，应重新登录，而不是继续重试可能已经轮换的旧刷新令牌。没有过期时间时，无法安排定时刷新。

核心辅助类不会在推理返回 `401` 后自动重放请求，也不会回退到配置中的 API Key。失败可能是需要重新授权、缺少 scope 或供应商不允许该 API。插件应提供明确提示，不要暴露可能含凭据的供应商响应正文。

`disconnect()` 删除本地凭据和待完成登录，不等于撤销供应商侧授权。需要撤销时，使用供应商的授权应用页面或专用撤销接口。在 `terminate()` 中，先调用 `session.close()`，再终止插件的供应商实例、用**原始类对象**注销适配器，最后关闭插件持有的令牌 HTTP 客户端。关闭 session 会保留持久化凭据，但阻止旧实例继续认证；已经发出的推理请求不会被追回。

`unregister_provider_adapter(type_name, provider_class)` 会检查类对象身份，旧插件实例不会误删替代类的注册。它不负责终止供应商实例，也不删除模型配置。插件供应商类型名称必须唯一。

只安装可信插件：插件能够在服务器执行 Python。私有 KV 命名空间和加密不是同进程恶意插件之间的沙箱；运行中的 AstrBot 进程被控制后，外部加密密钥也不能提供保护。

## 验证

```sh
uv run pytest tests/test_provider_oauth.py tests/test_provider_oauth_registration.py -q
uv run ruff check astrbot/core/provider/oauth.py astrbot/core/provider/register.py astrbot/api/provider examples/astrbot_plugin_oauth_provider
uv run ruff format --check astrbot/core/provider/oauth.py astrbot/core/provider/register.py astrbot/api/provider examples/astrbot_plugin_oauth_provider
```

测试使用虚构凭据和 HTTPX mock transport，不访问真实供应商。SDK 传输测试覆盖模型列表、普通 completion 和 SSE 流。真实供应商登录与浏览器到 Dashboard 的完整流程仍需用已注册客户端验证，不能据此宣称兼容所有供应商。
