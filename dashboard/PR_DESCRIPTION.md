<!--Please describe the motivation for this change: What problem does it solve? (e.g., Fixes XX issue, adds YY feature)-->
<!--请描述此项更改的动机：它解决了什么问题？（例如：修复了 XX issue，添加了 YY 功能）-->

创建新会话（`GET /api/chat/new_session`）后没有把“当前选择的配置文件（abconf）”绑定到该会话，导致新会话始终使用默认配置。  
本 PR 在新会话创建成功后，自动调用 `POST /api/config/umo_abconf_route/update` 将所选配置绑定到该会话对应的 UMO 路由；同时对 StandaloneChat（测试配置用）补齐相同的绑定逻辑，并统一 UMO/Storage Key 的生成规则与安全访问方式，避免多处实现不一致或在受限存储环境下抛异常导致绑定无效。

### Modifications / 改动点

<!--请总结你的改动：哪些核心文件被修改了？实现了什么功能？-->
<!--Please summarize your changes: What core files were modified? What functionality was implemented?-->

- `dashboard/src/composables/useSessions.ts`
  - 在 `newSession()` 创建会话成功后，读取最近一次选择的配置 id（`localStorage: chat.selectedConfigId`），并为 `webchat` 平台自动执行配置绑定：
    - 构造 UMO（与 `ConfigSelector.vue` 一致的 `platformId:messageType:sessionKey` 格式）
    - 调用 `POST /api/config/umo_abconf_route/update` 写入 `{ umo, conf_id }`
  - 绑定失败不会阻断会话创建（best-effort，保留默认配置作为回退）
- `dashboard/src/components/chat/StandaloneChat.vue`
  - Standalone 模式不走 `useSessions`，因此在其 `newSession()` 中同样在会话创建后调用 `/api/config/umo_abconf_route/update`，将 `props.configId` 绑定到新会话
- `dashboard/src/utils/chatConfigBinding.ts`
  - 抽出并复用公共逻辑：Storage Key 常量、读取/写入当前所选配置 id（带 try/catch 防护）、以及 webchat UMO 构造（避免多处手写字符串导致不一致或存储异常）
- `dashboard/src/components/chat/ConfigSelector.vue`
  - 复用 `chatConfigBinding.ts` 的安全存储访问与 username 读取（功能无变化，避免直接访问 `localStorage` 在受限环境下抛异常）
- `dashboard/src/components/chat/Chat.vue`
  - 清理调试日志（无业务逻辑变更）

- [x] This is NOT a breaking change. / 这不是一个破坏性变更。
<!-- If your changes is a breaking change, please uncheck the checkbox above -->

### Screenshots or Test Results / 运行截图或测试结果

<!--Please paste screenshots, GIFs, or test logs here as evidence of executing the "Verification Steps" to prove this change is effective.-->
<!--请粘贴截图、GIF 或测试日志，作为执行验证步骤的证据，证明此改动有效。-->

**Verification Steps / 验证步骤**

1. 启动后端（AstrBot Core），确保 Dashboard 可正常访问并能调用 API。
2. 启动 Dashboard：
   - `cd dashboard`
   - `pnpm dev`
3. 进入 Chat 页面，使用配置选择器选择一个非 `default` 的配置文件。
4. 创建新会话（点击“新会话/新对话”，或在无会话状态下直接发送消息触发创建）。
5. 在浏览器 DevTools → Network 中确认创建会话后出现一次：
   - `POST /api/config/umo_abconf_route/update`
   - 请求体中的 `conf_id` 为所选配置 id

**Local Checks / 本地检查**

- `pnpm run typecheck`（通过）

---

### Checklist / 检查清单

<!--If merged, your code will serve tens of thousands of users! Please double-check the following items before submitting.-->
<!--如果分支被合并，您的代码将服务于数万名用户！在提交前，请核查一下几点内容。-->

- [ ] 😊 如果 PR 中有新加入的功能，已经通过 Issue / 邮件等方式和作者讨论过。/ If there are new features added in the PR, I have discussed it with the authors through issues/emails, etc.
- [ ] 👀 我的更改经过了良好的测试，**并已在上方提供了验证步骤和运行截图**。/ My changes have been well-tested, **and "Verification Steps" and "Screenshots" have been provided above**.
- [x] 🤓 我确保没有引入新依赖库，或者引入了新依赖库的同时将其添加到了 `requirements.txt` 和 `pyproject.toml` 文件相应位置。/ I have ensured that no new dependencies are introduced, OR if new dependencies are introduced, they have been added to the appropriate locations in `requirements.txt` and `pyproject.toml`.
- [x] 😮 我的更改没有引入恶意代码。/ My changes do not introduce malicious code.
