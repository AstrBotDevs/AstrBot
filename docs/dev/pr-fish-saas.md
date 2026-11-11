# Pull Request: 大肥鱼鱼咖 SaaS（fish-api + fish-console）

> 用途：复制下方 **PR 正文** 到 GitHub Pull Request 描述框；标题见文末建议。

**建议目标仓库：** `Formyselfonly/AstrBot`（鱼咖魔改 fork）  
**不建议默认合入：** `AstrBotDevs/AstrBot`（除非已与上游约定产品化）

**基线对比：** `faba6c02d` … `HEAD`（2 commits：`1181b788d`、`61acc3a9e`）

---

## PR 正文（复制从这里开始）

<!--Please describe the motivation for this change: What problem does it solve? (e.g., Fixes XX issue, adds YY feature)-->
<!--请描述此项更改的动机：它解决了什么问题？（例如：修复了 XX issue，添加了 YY 功能）-->

### Motivation / 动机

**EN:** This change productizes the fork as **大肥鱼鱼咖** — a hosted QQ official-bot SaaS. End users manage accounts, top-ups, and bot binding via **fish-console**; **fish-api** owns tenant auth, commerce, usage, and proxy calls into the AstrBot engine; **AstrBot** (`main.py`, port **6185**) remains the conversation runtime. Upstream AstrBot documentation is preserved in [`docs/UPSTREAM-AstrBot-README.md`](../../docs/UPSTREAM-AstrBot-README.md); the repository root README is now customer/product facing. Product requirements and architecture live in [`PRD.md`](../../PRD.md) and [`技术方案.md`](../../技术方案.md).

**中文：** 将本仓库落地为 **大肥鱼鱼咖** 产品：客户无需自托管 Python/插件/密钥，通过用户中心完成注册、添饭、接鱼回家（绑定 QQ 开放平台机器人），在平台上查看用量与教程。业务逻辑集中在 **fish-api** / **fish-console**，尽量不与引擎核心耦合。对外统一品牌「大肥鱼鱼咖」；引擎仍基于 AstrBot 魔改，参考文档单独归档。

### Modifications / 改动点

<!--Please summarize your changes: What core files were modified? What functionality was implemented?-->
<!--请总结你的改动：哪些核心文件被修改了？实现了什么功能？-->

| 模块 | 说明 |
| --- | --- |
| **产品文档** | 新增 `PRD.md`、`技术方案.md`；根 `README.md` 重写（端口与服务一览）；上游 README 迁至 `docs/UPSTREAM-AstrBot-README.md`；移除根目录多语言 README |
| **fish-api** (`:8800`) | 独立 uv 工程：FastAPI + SQLAlchemy + Alembic（`alembic/` 在服务根目录）。路由：认证、钱包/订单、工单、用量、机器人绑定（`app/services/bot_bind.py`）、对接引擎（`app/providers/astrbot.py`）、用量计费（`app/services/usage_billing.py`）、管理员收银台（`admin_wallets`） |
| **fish-console** (`:5173`) | React + Vite 客户站：注册登录、套餐与支付宝添饭、接鱼向导、用量/订单/工单、管理员订单页；`/api` 代理至 fish-api |
| **客户教程** | `docs/customer/` Markdown + QQ 绑定截图（`docs/customer/assets/qq-bind/`） |
| **引擎 / 运营 UI 轻量** | `AGENTS.md` 补充本地端口说明；Dashboard 中文 header/auth 文案与 `index.html` title |

**数据与迁移：** `fish-api/alembic/versions/` 001–006（用户、绑定状态、memo、角色、渠道、用量游标等）。

**依赖：** 新 Python 依赖仅存在于 `fish-api/pyproject.toml`；前端依赖在 `fish-console/package.json`。根 AstrBot `pyproject.toml` 未新增鱼咖依赖。

- [x] This is NOT a breaking change. / 这不是一个破坏性变更。

<!-- If your changes is a breaking change, please uncheck the checkbox above -->

> **说明（fork 语义）：** 对 **上游 AstrBot 开源仓库消费者** 而言，根 README 与多语言 README 的替换属于产品化/品牌破坏性变更。本 PR 面向 **大肥鱼鱼咖魔改 fork**，不计划直接合入上游 `AstrBotDevs/AstrBot`。若目标仓库仍声明为纯 AstrBot 发行版，请将上方勾选改为破坏性变更并单独说明迁移路径。

### Verification Steps / 验证步骤

1. **fish-api 健康与注册**

   ```bash
   cd fish-api && cp -n .env.example .env && uv sync
   uv run alembic upgrade head
   uv run uvicorn app.main:app --reload --port 8800
   ```

   - http://127.0.0.1:8800/docs — `POST /api/v1/auth/register` → `GET /api/v1/auth/me`（Bearer）成功。
   - `curl -s http://127.0.0.1:8800/health` → `{"status":"ok"}`。

2. **fish-console 门户**

   ```bash
   cd fish-console && cp -n .env.example .env && pnpm install && pnpm dev
   ```

   - http://localhost:5173 — 注册/登录；可进入仪表盘、套餐、用量、接鱼页（8800 须已启动）。

3. **对话引擎 + 接鱼回家（完整链路）**

   - 仓库根目录：`uv sync && uv run main.py`（`:6185`）。
   - `fish-api/.env` 配置 `FISH_ASTRBOT_BASE_URL`、`FISH_ASTRBOT_API_KEY`（scopes 含 `config` + `bot`，见 `技术方案.md`）。
   - 用户中心按 QQ **图文教学 + 手填** AppID/AppSecret 完成绑定；可选验证微信扫码路径（见 `PRD.md` §3）。

4. **管理员收银台（可选）**

   - `FISH_ADMIN_EMAILS` 包含管理员邮箱；登录后侧边栏 **鱼咖收银台**（`/admin/orders`）。
   - 调碗 API 示例见 [`fish-api/README.md`](../../fish-api/README.md)。

### Screenshots or Test Results / 运行截图或测试结果

<!--Please paste screenshots, GIFs, or test logs here as evidence of executing the "Verification Steps" to prove this change is effective.-->
<!--请粘贴截图、GIF 或测试日志，作为执行“验证步骤”的证据，证明此改动有效。-->

| 项 | 状态 | 证据 |
| --- | --- | --- |
| `/health` | ⬜ 待贴 | `curl` 输出或截图 |
| 注册/登录 | ⬜ 待贴 | fish-console 截图 |
| 接鱼绑定 | ⬜ 待贴 | 绑定成功状态 + 可选 QQ 私聊 |
| OpenAPI | ⬜ 待贴 | 8800/docs 或 6185/api/v1/docs |

```text
# 示例（提交 PR 前替换为实测）
$ curl -s http://127.0.0.1:8800/health
{"status":"ok"}
```

教程配图已入库：`docs/customer/assets/qq-bind/01-open-platform.png` … `04-manual-params.png`。

---

### Checklist / 检查清单

<!--If merged, your code will serve tens of thousands of users! Please double-check the following items before submitting.-->
<!--如果分支被合并，您的代码将服务于数万名用户！在提交前，请核查一下几点内容。-->

- [ ] 😊 If there are new features added in the PR, I have discussed it with the authors through issues/emails, etc.  
  / 鱼咖为 fork 产品化；向 **第三方上游** 提 PR 前需沟通。（**自用 fork：可勾选并注明 N/A**）

- [ ] 👀 My changes have been well-tested, **and "Verification Steps" and "Screenshots" have been provided above**.  
  / 我的更改经过了良好的测试，**并已在上方提供了“验证步骤”和“运行截图”**。

- [ ] 📚 I checked the affected WebUI instructions and screenshots in `docs/zh` and `docs/en` against the changed navigation, page structure, and labels, and updated them in this PR (or explained why no documentation update is needed). For renamed, moved, or merged entry points, I included an **old entry → new entry** mapping in the documentation and changelog.  
  / **本 PR 说明：** 运营 Dashboard 仅少量 `dashboard/src/i18n/locales/zh-CN` 文案调整；**客户操作文档**在 `docs/customer/`，未系统性改动 `docs/zh`、`docs/en` 运营手册。无需更新或已在客户文档中覆盖 — 请 reviewer 确认后勾选。

- [x] 🤓 I have ensured that no new dependencies are introduced, OR if new dependencies are introduced, they have been added to the appropriate locations in `requirements.txt` and `pyproject.toml`.  
  / 新依赖在 **`fish-api/pyproject.toml`** 与 **`fish-console/package.json`**；根引擎依赖未为鱼咖扩容。

- [x] 😮 My changes do not introduce malicious code.  
  / 我的更改没有引入恶意代码。

---

## PR 正文（复制到这里结束）

---

## 建议 GitHub 标题

```
feat: add 大肥鱼鱼咖 SaaS (fish-api, fish-console, customer docs)
```

英文备选：

```
feat: add Fish SaaS customer portal and platform API
```

## 建议分支与提交（可选）

```bash
git checkout -b feat/fish-saas
# 若需 squash 两个「大肥鱼鱼咖」提交，可在 push 前 rebase -i
git push -u origin feat/fish-saas
gh pr create --base master --title "feat: add 大肥鱼鱼咖 SaaS (fish-api, fish-console, customer docs)" --body-file docs/dev/pr-fish-saas.md
```

> 使用 `--body-file` 时请只复制 **「PR 正文」** 两标记之间的内容，或单独维护 `docs/dev/pr-body-only.md`；上表中的本地路径链接在 GitHub 上会按仓库根目录解析。

## 里程碑对照（README 摘要）

| 能力 | PR 内实现度 |
| --- | --- |
| 邮箱注册 / 登录 / JWT | ✅ |
| 添饭 → `paid` / 订单流 | 部分（支付宝人工确认 + 管理员） |
| 接鱼回家（QQ 手填 + 微信扫码） | 实现依赖 `FISH_ASTRBOT_API_KEY` 与引擎在线 |
| 用量 × 服务系数 | 后端/页面骨架 + 计费服务，持续迭代 |

详见 [`PRD.md`](../../PRD.md) §6 里程碑。

---

*文档版本：2026-11-11 · 与分支 `master` @ `61acc3a9e` 对齐*
