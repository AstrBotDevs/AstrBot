# OAuth for plugin-defined AI providers

A plugin can register an AI provider and implement its login without adding a supplier to AstrBot core. `astrbot.api.provider.oauth` provides `OAuth2Session`, `OAuth2Token` and `OAuth2Error`. Supplier endpoints, client registration, scopes, user interface and credential storage remain plugin-owned.

This API implements the OAuth authorization-code flow for **public clients with PKCE S256**, plus refresh tokens. It does not implement device authorization, client secrets, OIDC identity verification, supplier-specific protocols or automatic callback hosting. A website login token is not necessarily an inference credential: the supplier must explicitly support your registered client and accept the resulting Bearer token at its AI API.

## Complete example

The repository's `examples/astrbot_plugin_oauth_provider/` directory contains a developer example with configuration schema, metadata, encrypted persistence and a [Plugin Page](./plugin-pages.md). It reuses AstrBot's OpenAI-compatible provider for model discovery, chat and streaming. It is not an integration with any particular supplier.

1. Register your own public OAuth client with a supplier that supports PKCE and OpenAI-compatible inference. Obtain its authorization endpoint, token endpoint, client ID, permitted scopes, registered redirect URI and API base. Do not copy a private client ID from another application.
2. Generate a storage-encryption key with the same Python environment used by AstrBot:

   ```sh
   python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
   ```

   Supply that value as `ASTRBOT_OAUTH_STORAGE_KEY` in AstrBot's process environment or deployment secret. Keep it stable across restarts and back it up separately from the database. Do not put it in plugin configuration, source control or browser storage. Losing the key requires signing in again.
3. Copy the example directory to `data/plugins/astrbot_plugin_oauth_provider/` in your AstrBot data directory. Configure the plugin in the WebUI, then reload it. The initial load intentionally fails until the environment key and OAuth settings are present.
4. Open the plugin's `oauth` Page from its detail view. Click **Start sign-in**, copy the authorization URL into a browser and approve the requested scopes. Paste the **complete redirected URL** into the Page and click **Complete sign-in**. The initiating Dashboard user must complete the attempt within ten minutes.
5. Add the **Plugin OAuth Example** provider in the Providers interface and select models. API keys stay empty; credentials come from the plugin. Its API destination is fixed by the plugin's `api_base`, not a model-level override. After a hot reload, use **Activate saved models** on the Page to reload existing model instances, or restart AstrBot. Normal startup already loads providers after plugins, so the plugin does not load them twice.

The example does **not** open a loopback listener. With its example redirect `http://127.0.0.1:14567/callback`, the browser may show a connection error after approval; copy the URL from the address bar. Use this only when the supplier permits that exact registered redirect. A supplier requiring automatic callbacks needs a separate, reviewed callback integration; do not make Dashboard extension APIs anonymous. The Dashboard itself should use HTTPS when accessed remotely.

The example shares **one account** across all models of its adapter. Its private KV key includes the supplier/client settings and scopes, preventing a configuration change from silently reusing credentials at another API. Old namespaces are retained; disconnect before changing configuration to remove the current account's stored credentials.

## Plugin API

```python
from astrbot.api.provider import (
    register_provider_adapter,
    unregister_provider_adapter,
)
from astrbot.api.provider.oauth import OAuth2Error, OAuth2Session, OAuth2Token
```

Construct one `OAuth2Session` per account with explicit, trusted endpoints and async `load_token()` / `save_token(token)` callbacks. Share the session across that account's models so refresh is serialized; sharing only a storage key across multiple sessions or processes does not coordinate token rotation. `save_token(None)` must delete the credentials, and save operations should be atomic. The core API does not encrypt storage automatically. The example encrypts its plugin-private KV value with Fernet, using the externally supplied key.

`begin_authorization(owner=...)` returns an authorization URL. Use `request.username` from `astrbot.api.web`, never an owner supplied in the request body. Pass the full redirect URL and the same authenticated owner to `complete_authorization(...)`. Use `cancel_authorization(owner=...)` to abandon an attempt without disconnecting an existing account. Starting another attempt replaces the pending one; closing the Page leaves it to expire.

For HTTPX-based providers, attach the session's request hook to the **inference client**, not the token client:

```python
client.event_hooks["request"].append(session.authorize_request)
client.follow_redirects = False
```

The example does this through the existing `_create_http_client` override. The hook attaches the current Bearer token after the SDK prepares a request. It covers model discovery and streaming without updating a shared SDK API-key field. Requests outside the configured API origin/path are refused before credentials are loaded. Keep this client dedicated to inference: do not reuse it to download arbitrary images or files.

Other transports can use `await session.get_access_token()` on the server, but must enforce their own destination and redirect checks. Do not expose this method through a Web API or return its result to the browser.

## Lifecycle and failure behavior

Tokens refresh shortly before their supplied expiry. Concurrent callers share one refresh operation; refresh-token rotation is persisted before use. A new sign-in never inherits the old account's refresh token. An `invalid_grant` response clears the local authorization. Transient failures are reported without clearing the stored account. A credential-storage failure fails closed; reconnect rather than retrying a potentially rotated old refresh token. Missing expiry means there is no known scheduled refresh time.

The helper does not automatically replay an inference request on `401` and does not fall back to a configured API key. The supplier's response may mean reauthorization, missing scopes or unsupported API access; the plugin should explain that to its users without exposing response bodies containing credentials.

`disconnect()` deletes local credentials and pending login. It does not revoke the supplier-side grant; use the supplier's authorized-apps page or a supplier-specific revocation implementation. In `terminate()`, first call `session.close()`, then terminate the plugin's provider instances, unregister the adapter with its **exact class**, and close the plugin-owned token HTTP client. Closing a session retains persisted credentials but blocks later authentication, including from old provider references. Already dispatched inference requests are not recalled.

`unregister_provider_adapter(type_name, provider_class)` is identity-checked: an old plugin instance cannot remove a replacement class's registration. It does not terminate providers or delete their saved configuration. Keep plugin-specific type names unique.

Only install trusted plugins: they execute server-side Python. Private KV namespaces and encryption do not sandbox one malicious plugin from another running in the same process. The encryption key also does not protect against a compromised running AstrBot process.

## Verification

```sh
uv run pytest tests/test_provider_oauth.py tests/test_provider_oauth_registration.py -q
uv run ruff check astrbot/core/provider/oauth.py astrbot/core/provider/register.py astrbot/api/provider examples/astrbot_plugin_oauth_provider
uv run ruff format --check astrbot/core/provider/oauth.py astrbot/core/provider/register.py astrbot/api/provider examples/astrbot_plugin_oauth_provider
```

Tests use fabricated credentials and HTTPX mock transports. The SDK transport test exercises model discovery, a non-streaming completion and an SSE stream without network access. A real supplier login and browser-to-Dashboard integration must additionally be checked with a properly registered client; these tests do not establish compatibility with every supplier.
