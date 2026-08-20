---
outline: deep
---

# Dashboard `data` 文件管理器设计方案

**状态**：设计审阅稿（产品决策已确认）

**目标**：在 Dashboard 中增加一个用于管理运行时 `data/` 目录的文件管理器，支持目录与文件的增删改查，并对常见文本文件提供编辑和语法高亮。

**非目标**：实现 code-server、OpenVSCode Server 或其他完整 Web IDE。不提供终端、代码执行、Git 工作流、语言服务器、远程协作或任意宿主机路径访问。

## 1. 设计结论

本功能应作为 Dashboard 的原生页面实现，而不是通过 iframe 嵌入一个独立 IDE。

当前 Dashboard 已经具备实现所需的主要基础：

- 前端已经依赖 `monaco-editor` 与 `@guolao/vue-monaco-editor`。
- Skills 页面已经实现了目录列表、文件读取、文件保存、编辑器状态、语言识别和主题切换。
- 后端已有基于 `Path` 的运行时目录 helper、Dashboard 登录态、统一授权和普通 JSON API envelope。
- 运行时目录由 `ASTRBOT_ROOT` 决定，不能在 Dashboard 中硬编码源码目录或开发者机器上的绝对路径。

因此，推荐的产品形态是：

```text
Dashboard
└── 数据文件
    ├── 左侧：data/ 目录树
    ├── 中间：文件标签页与 Monaco 编辑器
    └── 右侧/底部：文件信息、保存状态、操作反馈
```

这个页面应当把“文件系统访问”限制在 AstrBot 当前运行时的 `data/` 根目录，并对系统管理文件、敏感文件、数据库和二进制文件采用不同的操作策略。功能覆盖范围可以是整个 `data/`，但不能把所有路径当成普通文本文件无差别开放。

## 2. 背景与现状

### 2.1 当前前端基础

Dashboard 使用 Vue 3、Vuetify、Vue Router、Pinia 和 Axios。编辑器相关代码主要位于：

- `dashboard/src/utils/monacoLoader.ts`：Monaco Worker、语言定义和加载器配置。
- `dashboard/src/components/extension/SkillsSection.vue`：现有文件树与编辑器交互的最接近实现。
- `dashboard/src/components/shared/AstrBotConfig.vue` 与 `AstrBotConfigV4.vue`：配置项编辑器和主题切换。
- `dashboard/src/utils/shiki.ts` 与 `shikiLimitedBundle.ts`：只读 Markdown/代码高亮。

Skills 编辑器已经形成了当前 Dashboard 的视觉基线：

- 以 `v-card`、`v-dialog`、`v-list`、`v-menu` 和 `v-btn` 组成操作界面。
- 文件列表行使用紧凑密度、圆角、悬停背景和 active 背景，不引入新的色板。
- 编辑器容器使用 Dashboard surface、border 和 primary 透明色变量。
- Monaco 主题按 Skills 的既有映射跟随 Dashboard：`AstrBotDark` 使用 `vs-dark`，其他浅色主题使用 `vs-light`；默认关闭 minimap，启用自动布局和换行。
- 操作反馈使用现有 toast/snackbar 与错误提示，不使用浏览器原生 `alert`。

### 2.2 当前后端基础

Dashboard API 位于 `astrbot/dashboard/api/`，领域逻辑位于 `astrbot/dashboard/services/`。普通 JSON API 使用 `status`、`message`、`data` envelope；文件下载、图片、音频和其他原生协议响应不应强行包装成 JSON。

现有 Skills 文件 API 已经提供了本功能可以复用的安全模式：

- 只接受相对路径。
- 拒绝绝对路径和 `..` 路径片段。
- 使用 `resolve()` 后再次验证目标仍位于允许的根目录内。
- 对可编辑后缀和 UTF-8 内容进行限制。
- 对内置 Skill、插件 Skill 和 demo mode 施加只读约束。

新功能应提取通用能力，但不要把 Skills 的“技能名称”概念强行复用到整个 `data/` 文件系统。

### 2.3 `data/` 的运行时边界

运行时根目录由 `get_astrbot_root()` 返回，数据根目录由 `get_astrbot_data_path()` 返回。典型目录包括：

| 类别     | 典型路径                                                       | 内容性质                                   |
| -------- | -------------------------------------------------------------- | ------------------------------------------ |
| 配置     | `cmd_config.json`、`config/`                                   | 可能包含密码、Token、API Key 和运行时配置  |
| 数据库   | `data_v4.db`、`data.db`、`knowledge_base/*.db`                 | SQLite 数据及 WAL/SHM 文件，不适合文本编辑 |
| 插件     | `plugins/`、`plugin_data/`                                     | 插件源码、资源和插件持久化数据             |
| Skills   | `skills/`                                                      | 用户可编辑的 Skill 文件                    |
| 工作区   | `workspaces/`                                                  | Agent 或 WebChat 产生的用户文件            |
| 知识库   | `knowledge_base/`                                              | 文档、媒体、向量和元数据                   |
| 模板     | `t2i_templates/`                                               | HTML、CSS、JSON 等可编辑模板               |
| WebChat  | `webchat/`                                                     | WebChat 项目和用户内容                     |
| 依赖     | `site-packages/`                                               | 运行时 pip 安装内容，写入可能导致代码执行  |
| 备份     | `backups/`                                                     | 配置和知识库备份                           |
| 临时数据 | `temp/`、`attachments/`、`logs/`                               | 音频、图片、上传文件、日志和缓存           |
| 静态资源 | `dist/`                                                        | Dashboard 构建产物；写入可能造成持久 XSS   |
| 根级状态 | `shared_preferences.json`、`mcp_auth.json`、`.installation_id` | 运行时状态和认证辅助数据                   |

页面需要能够浏览所有目录，但“是否能读内容、是否能下载、是否能写入、是否能删除”应由文件类别和授权共同决定。

## 3. 目标与非目标

### 3.1 目标

1. 在 Dashboard 内浏览 `data/` 下的文件和目录（Phase 1）。
2. 在 Phase 2 创建、重命名、移动、删除文件和目录。
3. 在 Phase 2 上传普通文件，下载或预览已有文件。
4. 在 Phase 1 对常见文本文件进行读取和保存。
5. 在 Phase 1 根据文件名自动选择 Monaco 语言并提供语法高亮。
6. 在 Phase 1 保存前提示未保存修改，在并发变更时避免静默覆盖。
7. 使用现有 Dashboard 登录、授权、step-up 和审计机制。
8. 在桌面端和窄屏设备上保持可用，不破坏现有 Dashboard 视觉语言。
9. 不新增独立服务进程，不引入 code-server 运行时依赖。
10. 显示隐藏文件和以点号开头的目录，并对其应用同一套授权和安全策略。
11. 在 Phase 2 提供受权限约束的递归文件名搜索，不搜索文件内容。

### 3.2 非目标

以下能力不属于第一版：

- 终端、Shell、Python REPL 或“运行当前文件”。
- 在宿主机上安装依赖、启动进程或执行插件代码。
- LSP、调试器、编译器、代码补全服务器和 VS Code 扩展。
- Git 状态、提交、分支、冲突解决和远程仓库操作。
- 任意宿主机目录、源码目录、用户 Home 目录访问。
- 多人实时协作和实时文件 watcher。
- 直接修改 SQLite 数据库文件内容。
- 通过 `v-html` 渲染用户文件内容。
- 将文件内容放进 URL、日志、错误消息或审计记录。

## 4. 产品信息架构

### 4.1 页面入口

建议新增独立路由：

```text
/data
```

已确认 Sidebar 入口放在“更多”分组中，使用 `mdi-folder-cog-outline` 或同一语义的 MDI 图标。入口文案使用 i18n key，不在 `sidebarItem.ts` 中写死中文：

```text
core.navigation.dataFiles
```

如果后续确认该页面是高频入口，可以从“更多”提升为一级入口；第一版不改变现有 Sidebar 层级，避免增加主导航噪声。

建议新增路由记录：

```ts
{
  name: 'DataFiles',
  path: '/data',
  component: () => import('@/views/DataFilesPage.vue'),
}
```

页面必须继承现有 `FullLayout` 和认证路由，不创建独立登录态。

### 4.2 URL 状态

为了支持刷新、复制链接和浏览器后退，页面应保存当前选中的目录和文件路径：

```text
/data?path=skills/demo/SKILL.md
```

约束如下：

- URL 只保存相对 `data/` 根的路径，不保存绝对路径。
- URL 不保存文件内容、Token 或一次性下载凭据。
- 页面收到非法路径时回退到 `data/` 根目录并显示结构化错误。
- 文件未保存时离开页面，必须弹出统一的未保存变更确认对话框。

### 4.3 页面布局

桌面端布局：

```text
┌────────────────────────────────────────────────────────────┐
│ 页面标题   面包屑                  （Phase 2）上传  新建  更多 │
├───────────────┬────────────────────────────────────────────┤
│ data/         │ 标签页：SKILL.md  config.json  ...         │
│  ├ config     ├────────────────────────────────────────────┤
│  ├ plugins    │                                             │
│  ├ skills     │               Monaco 编辑器                 │
│  └ workspaces │                                             │
│               ├────────────────────────────────────────────┤
│               │ 行号 | 语言 | 编码 | 文件大小 | 保存状态    │
└───────────────┴────────────────────────────────────────────┘
```

建议尺寸：

- 左侧目录树初始宽度 280px，允许拖拽到 220–420px。
- 编辑器区域占用剩余空间，最小高度 520px。
- 目录树与编辑器之间使用现有 border 变量，而不是新的灰色常量。
- 页面顶部沿用现有页面标题、面包屑和操作按钮间距。

移动端布局：

- 目录树变为可展开的 `v-navigation-drawer` 或 `v-dialog`。
- 编辑器占满页面宽度。
- 文件操作从顶部按钮收纳到 `v-menu`。
- 打开文件后默认收起目录树，保留“返回目录”按钮。

## 5. 视觉设计规范

### 5.1 颜色与表面

不新增品牌色。使用 Vuetify 和 Dashboard 现有 CSS 变量：

- `rgb(var(--v-theme-surface))`
- `rgb(var(--v-theme-surface-variant))`
- `rgb(var(--v-theme-on-surface))`
- `rgb(var(--v-theme-on-surface-variant))`
- `rgb(var(--v-theme-primary))`
- `var(--v-theme-border)`

文件列表状态建议：

| 状态     | 表现                                                  |
| -------- | ----------------------------------------------------- |
| 默认     | `on-surface` 文字，透明背景                           |
| 悬停     | `rgba(on-surface, 0.06)` 背景                         |
| 当前文件 | `rgba(on-surface, 0.10)` 背景，primary 图标或左侧标记 |
| 未保存   | 文件名右侧显示小圆点，颜色使用 warning                |
| 只读     | 锁图标和 `on-surface-variant` 文字                    |
| 错误     | 使用现有 error 色和 `v-alert`/toast                   |
| 受保护   | 使用 shield 图标，不使用醒目的纯红背景                |

### 5.2 组件与圆角

- 使用 Vuetify 现有 `v-card`、`v-list`、`v-list-item`、`v-menu`、`v-dialog` 和 `v-btn`。
- 文件树行保持 34–36px 的紧凑高度，适合长目录浏览。
- 编辑器容器采用 10px 左右圆角、1px border 和轻微 primary outline，匹配 Skills 编辑器。
- 重要删除操作使用统一确认对话框，不直接使用 `window.confirm`。
- 操作按钮优先使用图标 + tooltip；窄屏下可以只显示图标。
- 目录和文件图标使用 MDI，颜色只表达类型或状态，不为每种扩展名建立新颜色体系。

### 5.3 编辑器设置

第一版沿用 Skills 编辑器的设置：

```ts
{
  automaticLayout: true,
  fontSize: 13,
  lineNumbers: 'on',
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  tabSize: 2,
  wordWrap: 'on',
}
```

`readOnly` 由后端返回的 `writable`、文件策略和当前加载状态共同决定。主题按 Skills 的既有映射选择：`AstrBotDark` → `vs-dark`，其他浅色主题 → `vs-light`，不单独维护第三套编辑器主题。

## 6. 文件类型与操作策略

### 6.1 文件类型判定

后端返回规范化后的文件类型和能力，前端不自行推断安全权限。前端只根据 `language` 选择编辑器语言。

建议的基础字段：

```ts
type DataEntryType = 'file' | 'directory' | 'symlink' | 'other';

interface DataEntry {
  name: string;
  path: string;
  type: DataEntryType;
  size: number;
  modified_at: string;
  category: 'text' | 'binary' | 'database' | 'system' | 'temporary';
  language: string | null;
  readable: boolean;
  writable: boolean;
  deletable: boolean;
  downloadable: boolean;
  protected: boolean;
}
```

分类必须由后端统一完成，且遵循“路径前缀优先于扩展名”的顺序：先判断路径是否属于系统管理、插件、数据库或临时目录，再对被判定为普通文本的文件按文件名和扩展名推断 `language`。扩展名不能把受保护路径洗白成普通文本。

典型结果如下：

| 路径                   | 分类与能力                                                               |
| ---------------------- | ------------------------------------------------------------------------ |
| `dist/index.html`      | `category=system`，默认不可写；不能仅因 `.html` 进入普通 Monaco 可写模式 |
| `plugins/foo.py`       | `category=system`，默认只读；不能仅因 `.py` 进入普通 Monaco 可写模式     |
| `plugin_data/foo.json` | 普通数据，按扩展名识别为文本；不继承 `plugins/` 的只读策略               |
| `workspaces/foo.json`  | 普通文本，可按普通文件授权处理                                           |

移动、重命名和创建操作必须同时按源路径和目标路径重新分类并重新计算能力；不能通过移出 `plugins/` 或移入 `dist/` 改变安全类别。`plugin_data/` 与 `plugins/` 分开处理：前者默认作为普通插件持久化数据可写，后者默认只读。

### 6.2 文本文件

第一版建议支持以下语言映射：

| 扩展名或文件名             | Monaco language           |
| -------------------------- | ------------------------- |
| `.json`                    | `json`                    |
| `.yaml`、`.yml`            | `yaml`                    |
| `.toml`、`.ini`            | `ini`                     |
| `.py`                      | `python`                  |
| `.js`、`.mjs`、`.cjs`      | `javascript`              |
| `.ts`                      | `typescript`              |
| `.html`                    | `html`                    |
| `.css`、`.scss`            | `css`                     |
| `.sh`、`.bash`             | `shell`                   |
| `.md`、`.markdown`、`.txt` | `markdown` 或 `plaintext` |
| `.sql`                     | `sql`                     |
| `.xml`                     | `xml`                     |
| `.ps1`                     | `powershell`              |
| `Dockerfile`               | `dockerfile`              |
| `Makefile`                 | `plaintext`               |

文件名匹配应优先于扩展名。未知后缀仍可在“以文本打开”操作中使用 `plaintext`，但不能绕过后端的二进制检测和大小限制。

### 6.3 二进制文件

二进制文件不能直接送入 Monaco。页面根据 MIME 和文件大小选择：

- 图片：在安全的图片预览组件中显示，并提供下载。
- 音频：使用受控的音频播放器，并提供下载。
- 视频：第一版只提供下载，避免引入新的媒体布局和流式缓存问题。
- 压缩包、字体、数据库和未知二进制：显示元数据、下载和删除操作。
- SVG：默认按下载处理，不把不可信 SVG 直接注入 DOM；如果未来提供预览，必须经过严格清洗或转为图片。

### 6.4 系统管理文件

以下路径可能影响运行时或包含秘密，不能沿用普通文件的默认操作策略：

- `cmd_config.json`、`config/`、`mcp_server.json`。
- `data_v4.db`、`data.db`、`*.db-wal`、`*.db-shm`。
- `knowledge_base/` 中的数据库、FAISS 索引和内部 metadata。
- `site-packages/`、`dist/` 构建产物。
- `backups/`、`webchat/` 中由运行时管理的状态和项目数据。
- `shared_preferences.json`、`mcp_auth.json`、`.installation_id` 等根级状态文件。
- 运行时生成的认证、安装和升级状态文件。

已确认 root Dashboard session 可以读取 `cmd_config.json` 和 `config/` 的原始内容。建议采用三层控制：

1. 所有文件都可以在目录树中显示基本元数据，包括以点号开头的隐藏项。
2. 读取、下载、写入和删除分别由后端返回能力控制，不因“能看到”而默认能操作。
3. 原始配置内容读取属于 root Dashboard session 的敏感读取分支；`Role.OPERATOR` 继续使用现有脱敏 Config API，不通过普通文件读取绕过脱敏。
4. `site-packages/`、`dist/`、活跃数据库及其 WAL/SHM、认证辅助状态默认不可写；不能仅靠 step-up 把这些路径变成普通可写目录。
5. 其他受保护文件可以在 `filesystem.manage` 的一次性 step-up 后删除；数据库和正在使用的运行时资源仍可由 service 根据占用状态硬拒绝。

对于 `cmd_config.json` 等配置，页面仍优先显示“在结构化配置页中编辑”的入口；root Dashboard session 可以使用原始编辑。原始保存不能直接写字节：服务必须先解析并验证内容，再委托对应配置服务执行持久化，并在成功后自动触发关联运行时 reload。任何验证或 reload 失败都必须返回结构化错误、保留编辑器中的未保存内容，且不能留下“磁盘新配置、内存旧配置”的半提交状态。该托管文件规则还必须逐类覆盖 `config/*.json`、`mcp_server.json`、Skills、T2I 模板以及其他会被 manager 缓存的文件；如果某一类暂时没有可靠 reload，v1 必须明确标记为“只改磁盘，不保证运行时立即生效”。

## 7. 后端设计

### 7.1 模块划分

建议新增：

```text
astrbot/dashboard/api/data_files.py
astrbot/dashboard/services/data_file_service.py
astrbot/dashboard/schemas.py                    # 请求/响应模型
dashboard/src/api/v1/dataFiles.ts               # 前端 API 封装
dashboard/src/views/DataFilesPage.vue           # 页面
dashboard/src/components/data-files/             # 页面组件
```

`DataFileService` 负责运行时文件系统操作，API 路由只负责：

- 认证和授权依赖。
- 请求参数和 header 解析。
- 调用 service。
- 将领域错误转换为统一 API 错误。

不要把 `Path` 操作散落在 Vue 组件、API 路由或通用工具函数中。

文件管理路由直接复用现有的 `require_dashboard_session_principal` dependency：它验证 Dashboard JWT/session principal，并在发现 API Key、无效 Bearer 或缺失 Cookie 时直接返回 403/401。不能新造另一套认证体系，也不能通过 `require_scope("file")`、`require_scope("data")` 或其他会接受 API Key 的旧 scope 进入该服务。

### 7.2 根目录解析

服务初始化时通过 `get_astrbot_data_path()` 获取数据根目录，并在每次请求中对用户路径执行安全解析：

```python
data_root = Path(get_astrbot_data_path()).resolve(strict=True)
candidate = (data_root / normalized_relative_path).resolve(strict=False)

if not candidate.is_relative_to(data_root):
    raise DataFileServiceError("Invalid data path")
```

实际实现还必须处理：

- 空路径表示 `data/` 根目录。
- 反斜杠统一为 `/` 后再解析。
- 拒绝绝对路径、空路径片段、`.` 和 `..` 片段；以点号开头的合法名称不属于隐藏或拒绝条件。
- 不跟随逃出根目录的符号链接。
- 对符号链接本身只显示元数据，不默认遍历目标。
- 处理目标在请求期间被删除或替换的竞态。
- `resolve()` 之后、`open()` 之前仍需防范 TOCTOU；POSIX 使用 `O_NOFOLLOW` 或打开后 `fstat` 校验，其他平台使用等价的“打开后再验证”策略。
- 原子保存临时文件使用保留前缀，并在目录列表中默认过滤，避免用户看到内部半成品。
- Windows 驱动器号、大小写和保留文件名。

### 7.3 API 草案

新 API 使用 `/api/v1/data-files` 前缀，并使用独立的 `Data Files` OpenAPI tag，不能复用现有附件 API 的 `Files` tag。普通 JSON 路由使用标准 envelope，下载和原生媒体预览使用 raw response。

| 方法     | 路径                               | 作用                       |
| -------- | ---------------------------------- | -------------------------- |
| `GET`    | `/data-files/tree?path=`           | 列出目录的直接子项         |
| `GET`    | `/data-files/metadata?path=`       | 获取文件或目录元数据       |
| `GET`    | `/data-files/content/{path:path}`  | 读取 UTF-8 文本内容        |
| `GET`    | `/data-files/download/{path:path}` | 下载原始文件               |
| `POST`   | `/data-files/entries`              | 创建文件或目录             |
| `PUT`    | `/data-files/content/{path:path}`  | 写入文本内容               |
| `POST`   | `/data-files/upload`               | 上传二进制或文本文件       |
| `GET`    | `/data-files/search?q=&path=`      | 在允许范围内递归搜索文件名 |
| `PATCH`  | `/data-files/entries`              | 重命名或移动文件/目录      |
| `DELETE` | `/data-files/entries/{path:path}`  | 删除文件或目录             |

接口契约可以在设计阶段一次列全，但 Phase 1 只实现 `tree`、`metadata`、文本 `content` 读取与保存；`entries`、`upload`、`search` 和 `download` 的新增能力按 Phase 2 的权限与安全策略交付，不应在 Phase 1 的验收中视为已实现。

建议请求示例：

```json
{
  "path": "skills/demo/SKILL.md",
  "content": "# Demo Skill\n",
  "encoding": "utf-8",
  "expected_etag": "sha256:..."
}
```

建议文件读取响应：

```json
{
  "status": "ok",
  "message": "",
  "data": {
    "path": "skills/demo/SKILL.md",
    "content": "# Demo Skill\n",
    "size": 13,
    "encoding": "utf-8",
    "language": "markdown",
    "etag": "sha256:...",
    "writable": true,
    "protected": false
  }
}
```

目录列表响应只返回直接子项，不返回文件内容：

```json
{
  "status": "ok",
  "message": "",
  "data": {
    "path": "skills/demo",
    "entries": [
      {
        "name": "SKILL.md",
        "path": "skills/demo/SKILL.md",
        "type": "file",
        "size": 13,
        "category": "text",
        "language": "markdown",
        "readable": true,
        "writable": true,
        "deletable": true
      }
    ]
  }
}
```

### 7.4 创建、移动和删除

创建接口必须明确区分 `file` 和 `directory`：

```json
{
  "path": "workspaces/demo/notes.md",
  "type": "file",
  "content": ""
}
```

约束：

- 不自动创建用户没有明确请求的多级父目录，或者提供显式 `create_parents` 选项并限制在 `data/` 内。
- 新文件名不能包含路径分隔符、控制字符或平台保留名。
- 移动操作必须重新验证源路径和目标路径，不能只拼接字符串。
- 默认只允许删除空目录；递归删除必须显式传入确认字段。受保护目录和文件允许在 `filesystem.manage` + 一次性 step-up 后删除，不设永久前端禁用；后端仍可针对正在使用或无法安全删除的运行时资源拒绝请求。
- 删除前后都写脱敏审计事件，只记录相对路径摘要、类别、大小和操作主体，不记录文件内容。

### 7.5 上传与下载

- 上传使用 multipart，文件名必须经过 basename 和保留字符校验。
- Phase 2 单文件上传上限为 32 MiB、单次上传请求上限为 64 MiB，且始终不得超过 Dashboard 的全局请求体限制；上传流不能先完整载入内存。
- 不自动解压上传的 zip/tar 文件，避免路径穿越和压缩炸弹。
- 下载必须设置安全的 `Content-Disposition`，防止浏览器把不可信内容当作页面执行。
- 下载复用 `content_disposition_header()` 的 RFC 6266 编码实现，不在新路由中手写 header 拼接。敏感文件的下载和预览必须与敏感内容读取使用相同的 root 限制，并建议额外消费一次性 step-up（与 `data.export_all` 的策略对齐）；不能让 `Role.OPERATOR` 通过 `/download` 绕过 Config API 的脱敏。
- 下载 URL 不携带 Dashboard JWT 或 API Key。
- 二进制预览使用经过认证的原始响应，不能把任意文件路径拼成公开静态 URL。

### 7.6 并发保存与原子性

写入必须避免“编辑器打开期间文件被其他任务覆盖”以及“写到一半进程崩溃留下半个文件”：

1. 读取时计算并返回 `etag`，推荐使用内容 SHA-256。
2. 保存时提交 `expected_etag` 或 `If-Match`。
3. 当前文件 etag 与预期不一致时返回 `409 Conflict`，前端显示差异选择对话框。
4. 写入同目录临时文件，完成 flush/fsync 后使用原子替换。
5. 替换前可按配置创建有限数量的 `.bak` 快照，不能无限生成备份。
6. 失败时清理临时文件，原文件保持不变。

`cmd_config.json` 等由配置服务管理的文件不能绕过 `AstrBotConfig.save_config_async()`。原始编辑保存必须走“解析和验证 → 配置服务持久化 → 关联运行时 reload”的单一提交路径，而不是先直接写文件再尝试 reload。`config/{plugin}.json` 等插件配置文件不应假定复用 `AstrBotConfig.save_config_async()`，应由其现有配置服务或插件配置管理器负责持久化和 reload；没有可靠 reload 的类别必须明确标记为“只改磁盘，不保证运行时立即生效”。

## 8. 授权与安全模型

### 8.1 权限建议

建议新增文件系统专用能力，不复用附件的 `file` scope 或知识库的 `data` scope。新路由必须使用 Dashboard session authentication，并明确拒绝 API Key；否则默认 API Key scope 会把附件或数据权限错误扩大到整个 `data/` 根目录。

```text
filesystem.read
filesystem.write
filesystem.manage
```

动作注册要求：

- `filesystem.read`：`Role.OPERATOR` + `Role.ROOT`，普通目录和文件读取；敏感原始配置读取由 service 额外限制为 root Dashboard session。
- `filesystem.write`：`Role.OPERATOR` + `Role.ROOT`，普通文件的创建、上传、修改、重命名、移动和删除。
- `filesystem.manage`：`Role.ROOT`，高风险动作；用于原始配置写入、`plugins/` 写入、受保护文件删除和其他敏感管理操作，必须消费一次性 step-up。
- 三个动作都必须加入 `ACTIONS`、`ACTION_ROLE_GRANTS` 和对应测试；仅 `filesystem.manage` 加入 `HIGH_RISK_ACTIONS`。`filesystem.*` 必须在 `_resource_types_for()` 中映射到新资源类型。

不要把 `system.manage` 当作 step-up 开关。它当前是 root-only 但不是高风险动作，直接改变其风险属性会让 Backup、Logs、Cron、Stats 等现有 system 路由产生无关的 step-up 行为。

资源使用现有 canonical helper：

```text
Resource.named("filesystem", "collection")
object_resource("filesystem", relative_path)
```

集合资源使用 `Resource.named("filesystem", "collection")`；单路径资源使用现有 `object_resource("filesystem", relative_path)`。不要把任意相对路径直接作为 `Resource.named()` 的 ID：其 ID 校验不接受 Unicode、空格或过长路径。实现中应通过这些 canonical helper 生成 `type:v1:...` 资源 ID，不自造 `data-path:<sha256>` 形式。路径 hash 可以作为 step-up 绑定的内部摘要，但 v1 不建立每路径 role grant。Dashboard UI 默认使用当前 Dashboard session principal；API Key 直接返回 403。

### 8.2 操作分级

| 操作        | 普通文件           | 敏感文件                                          | 数据库/运行时状态       |
| ----------- | ------------------ | ------------------------------------------------- | ----------------------- |
| 列出元数据  | `filesystem.read`  | `filesystem.read`                                 | `filesystem.read`       |
| 读取内容    | `filesystem.read`  | `Role.ROOT` + `filesystem.read`                   | 默认拒绝或只读下载      |
| 下载/预览   | `filesystem.read`  | `Role.ROOT` + `filesystem.read`，建议额外 step-up | 默认拒绝或只读下载      |
| 创建/上传   | `filesystem.write` | `filesystem.manage` + step-up                     | 默认拒绝                |
| 修改        | `filesystem.write` | `filesystem.manage` + step-up                     | 默认拒绝                |
| 重命名/移动 | `filesystem.write` | `filesystem.manage` + step-up                     | 默认拒绝                |
| 删除        | `filesystem.write` | `filesystem.manage` + step-up                     | 活库/运行时占用时硬拒绝 |

`plugins/` 默认只读；只有 `filesystem.manage` + 一次性 step-up 后，后端才为该路径返回可写能力。`dist/`、`site-packages/`、活跃数据库及其 WAL/SHM 永远不进入普通可写路径；step-up 不能把潜在 RCE 或正在使用的运行时文件变成安全的普通文件。demo mode 必须保持只读。所有授权判断应在后端执行，前端的 `writable` 等字段只用于呈现状态，不能作为安全边界。

### 8.3 敏感内容处理

文件编辑器是有意让 root Dashboard session 读取原始文件，因此不能简单依赖通用 API 脱敏替换内容。但仍应做到：

- 只在明确授权后返回敏感文件原文。
- 错误响应、访问日志和审计日志不记录文件内容。
- 前端不把文件内容放入 URL、localStorage 或 Pinia 持久化状态。
- 关闭标签页后释放 Monaco model，避免大文件内容长期留在内存。
- 浏览器离开页面时清理临时预览 Blob URL。
- 任何 Markdown、HTML、SVG 预览都必须经过安全渲染流程；第一版优先使用纯文本或下载。

## 9. 前端组件设计

### 9.1 组件树

v1 不把页面拆成大量一次性 wrapper；先保持四个主要组件，只有在交互重复或测试边界稳定后再提取细粒度组件：

```text
DataFilesPage.vue
├── DataFileTree.vue
├── DataFileWorkspace.vue
│   ├── tabs / breadcrumbs / status
│   ├── Monaco editor / binary preview
│   └── file action dialogs
└── DataFileSearch.vue              # Phase 2
```

页面状态可以由 `useDataFiles()` composable 统一维护，或在确认存在跨页面共享需求后再抽成 Pinia store。第一版不把文件内容持久化到全局 store。

### 9.2 目录树

目录树行为：

- 只在展开目录时请求其直接子项。
- 目录行显示展开箭头、文件夹图标、名称和受保护标识；隐藏项额外显示低干扰的“隐藏”标记或点号图标。
- 文件行显示类型图标、名称、未保存圆点和只读锁。
- 当前路径高亮，支持键盘上下移动和 Enter 打开。
- 右键或行尾菜单提供新建、重命名、移动、删除、下载。
- 目录超过后端返回的分页或数量上限时，显示“加载更多”，不静默截断。
- 符号链接不展开，显示链接图标和受限提示。

### 9.3 标签页

每个打开文件对应一个 Monaco model 和标签页：

- 标签页标题使用 basename，tooltip 显示完整相对路径。
- 未保存文件显示圆点，不改变文件名颜色。
- 关闭未保存标签时弹出确认。
- 打开同一文件复用已有 model，不创建重复标签。
- 后端返回 `409` 时保留本地内容，v1 只显示“保留本地 / 重新加载”两项选择；不在第一版实现差异复制或强制覆盖。
- 标签页数量过多时提供关闭其他、关闭右侧和关闭全部操作。

### 9.4 编辑器与预览

`DataFileEditor` 根据 `category` 和 `language` 选择模式：

- `text`：Monaco 编辑器。
- `binary`：元数据 + 下载，图片和音频可使用安全预览。
- `database`：元数据 + 下载/删除策略，不显示编辑器。
- `system`：根据后端能力显示只读编辑器或引导到配置页面。
- `temporary`：默认只读，提供清理操作。

编辑器保存状态至少包括：

```ts
type EditorStatus =
  'idle' | 'loading' | 'dirty' | 'saving' | 'saved' | 'conflict' | 'error';
```

### 9.5 快捷键和可访问性

第一版支持：

- `Ctrl/Cmd+S` 保存当前文件。
- 文件名搜索快捷键（建议 `Ctrl/Cmd+K`）放入 Phase 2；Phase 1 不注册会与浏览器冲突的全局搜索快捷键。
- `Escape` 关闭菜单或对话框，不丢失编辑内容。
- 文件树支持可见的焦点状态、ARIA label 和键盘操作。
- 操作按钮提供 tooltip 和 `aria-label`，不能只依赖图标。
- 颜色不是传达只读、未保存或错误的唯一方式，必须同时使用图标、文字或状态区域。

## 10. 搜索与性能

### 10.1 Phase 2 搜索范围

Phase 2 实现受权限约束的递归文件名搜索：

- 默认在 `data/` 根下搜索；用户可将范围收窄到当前目录。
- 后端仅搜索 basename 和相对路径，不读取或索引文件内容。
- 搜索使用 `asyncio.to_thread`，默认最多返回 100 项，并设置 inode 预算（建议 5000）和 3 秒超时；超时返回已找到结果与 `truncated: true`，不持续占用事件循环。
- 搜索结果必须经过与目录树相同的路径分类和授权过滤；没有读取权的文件不出现在结果中。
- 搜索关键字、结果路径和文件内容不写入审计正文或持久化浏览器状态。

已打开文件内的 Monaco 查找由编辑器原生提供。全文内容搜索会牵涉大量二进制文件、权限过滤、敏感内容泄露和索引生命周期，保留为后续能力；若实现，必须由后端在允许的文件集合内执行，不能让前端递归下载整个 `data/`。

### 10.2 性能边界

建议初始默认值：

- 单个可编辑文本文件上限：1 MiB；超过后只读下载。现有 Skills API 的 512 KiB 限制继续保持，通用 data 文件 API 不应静默放宽 Skills 专用边界。
- 单目录首次返回上限：200 项，后端支持分页或继续加载。
- 单文件上传上限：32 MiB；单次上传请求上限：64 MiB，同时保留 Dashboard 现有全局上限作为硬上限。
- Monaco 同时保留的 model 数量设上限，关闭标签时主动 dispose。
- 目录元数据可以按 etag 或修改时间短暂缓存，但不能缓存敏感文件内容到浏览器持久存储。

这些值应放入后端常量或配置元数据，不在 Vue 组件中散落硬编码。

## 11. OpenAPI 与代码生成

新增或修改 Dashboard API 时必须同步：

1. `openspec/openapi-v1.yaml`。
2. Dashboard 生成客户端 `dashboard/src/api/generated/openapi-v1/`。
3. `docs/public/openapi.json`（如果该接口属于公开文档范围）。
4. 后端 API 测试、Dashboard API 封装和前端组件测试。

生成流程遵循 [Dashboard OpenAPI 开发说明](/dev/openapi) 和项目架构文档中的生成命令。生成客户端不能手工编辑。

文件管理器的 Dashboard-only 路由不应加入公开 API Key surface。公开文档由 tag 白名单裁剪，因此 `Data Files` 不加入 `PUBLIC_OPEN_API_TAGS`；不能仅靠前端隐藏入口。

## 12. 测试方案

### 12.1 后端单元测试

至少覆盖：

- 空路径、普通相对路径和 Unicode 文件名。
- 以点号开头的隐藏文件和目录。
- 绝对路径、`..`、反斜杠穿越和 URL 编码穿越。
- 根目录符号链接、内部符号链接和断开的符号链接。
- 文件、目录、特殊文件和不存在路径。
- UTF-8 文本、非法 UTF-8、二进制文件和超大文件。
- 创建、重命名、移动、删除和递归删除确认。
- 非空目录删除、受保护路径删除和 demo mode 写入。
- etag 匹配、etag 冲突、并发保存和原子替换失败。
- 临时文件清理与异常情况下原文件不变。
- `cmd_config.json` 等系统管理文件的授权和 step-up。
- 原始配置保存的校验失败、持久化失败、reload 失败和完整成功路径。
- `plugins/` 默认只读及其 step-up 写入。
- 文件名搜索的权限过滤、结果上限和超时截断。
- 审计记录不包含文件内容、Token 或绝对路径。

测试必须使用临时 runtime root 或 fixture，不能读取或覆盖开发者真实 `data/`。这与源码开发文档中关于 `ASTRBOT_ROOT` 和临时目录的约束一致。

### 12.2 Dashboard 单元测试

至少覆盖：

- 路由和页面初始加载。
- 目录展开的懒加载和错误状态。
- 隐藏项展示、图标和受保护标记。
- 文件打开、重复打开复用标签和关闭标签。
- Monaco 语言映射和暗色/亮色主题。
- 未保存状态、离开确认和保存成功反馈。
- `409 Conflict` 的冲突对话框。
- 只读、受保护、二进制和数据库文件展示。
- 新建、重命名、移动、删除对话框。
- Phase 2 的上传、递归文件名搜索和搜索结果打开。
- 窄屏抽屉布局和键盘操作。
- i18n 中 zh-CN 与 en-US key 结构保持一致。

可以复用现有 `SkillsSection`、`templateListEditor` 和页面 smoke test 中的 Monaco mock 模式。

### 12.3 E2E 测试

E2E 应使用独立的临时 runtime root，验证完整链路：

1. 登录 Dashboard。
2. 打开“数据文件”页面。
3. 展开目录并创建文本文件。
4. 编辑、保存并刷新页面。
5. 验证目录树和内容持久化。
6. 验证外部修改触发冲突提示。
7. 验证二进制文件上传、下载和敏感路径的 step-up。
8. Phase 2 验证递归文件名搜索、隐藏项展示、删除目录和未保存离开确认。

## 13. 分阶段实施

### Phase 0：契约和安全基础

- 新增 `DataFileService`、路径解析器和文件分类器。
- 只实现目录树和文件 metadata API。
- 完成授权、审计、路径穿越和符号链接测试。
- 明确系统管理路径清单。

### Phase 1：浏览与文本文件编辑

- 新增 `/data` 页面和 Sidebar 入口。
- 实现目录树、文件标签、Monaco 编辑和保存。
- 接入 etag 冲突检测、原子保存和未保存提示。
- 支持现有语言映射和主题。
- 显示隐藏文件，但先不提供递归搜索和上传。
- 对 `skills/`、T2I 模板等已有 manager 缓存的普通文本文件，Phase 1 明确标记为“只改磁盘，不保证运行时立即 reload”；原始配置保存和受保护路径写入不属于本阶段。

### Phase 2：上传、搜索与受保护路径

- 新建文件和目录。
- 新建、重命名、移动、删除、上传和下载。
- 增加二进制元数据和安全预览。
- 增加递归文件名搜索，使用 `asyncio.to_thread`、inode 预算和超时截断。
- 增加受保护路径、`plugins/` 写入和受保护删除的 `filesystem.manage` + step-up 流程。
- 让 `cmd_config.json` 等核心配置走校验、持久化和自动 runtime reload 的单一提交路径；`config/{plugin}.json` 由其现有配置服务或插件配置管理器负责，不假定复用 `AstrBotConfig.save_config_async()`。

### Phase 3：审阅后增强

可选能力：

- 受控的全文搜索。
- 有限版本/备份恢复。
- 文件变化提示，但不引入实时协作协议。
- 针对插件开发目录的只读/开发模式切换。

## 14. 验收标准

### 功能

- [ ] Phase 1 能浏览 `data/` 及其所有下级目录的元数据。
- [ ] Phase 2 能创建、读取、更新、重命名、移动和删除允许范围内的文件/目录。
- [ ] Phase 1 文本文件能在 Monaco 中编辑并保存。
- [ ] Phase 1 常见扩展名能自动选择正确的语法高亮。
- [ ] Phase 1 二进制文件不会被当作文本加载。
- [ ] Phase 2 能上传不超过 32 MiB 的文件，并执行受权限约束的递归文件名搜索。
- [ ] Phase 1 能显示以点号开头的文件和目录。
- [ ] Phase 1 页面刷新后目录和文件状态正确恢复。

### 安全

- [ ] 任何请求都不能访问 `data/` 之外的路径。
- [ ] 符号链接不能逃出 `data/` 根目录。
- [ ] 普通 Dashboard 用户不能绕过后端能力字段修改受保护文件。
- [ ] 敏感操作按授权和 step-up 规则执行。
- [ ] `plugins/` 默认只读，只有 step-up 后可写。
- [ ] 删除和写入操作有脱敏审计记录。
- [ ] 日志、错误响应和 URL 中没有文件内容、Token 或绝对路径。

### 一致性

- [ ] 并发修改会返回冲突，而不是静默覆盖。
- [ ] 保存失败不会留下半个文件或错误覆盖原文件。
- [ ] 配置管理文件不会绕过现有异步配置保存机制。
- [ ] 原始配置保存会在提交后自动触发关联运行时 reload，失败不产生半提交状态。
- [ ] 删除、移动和重命名不会留下未清理的临时文件。

### 视觉与体验

- [ ] 页面使用现有 Vuetify、surface、border、primary 和主题变量。
- [ ] 暗色和亮色主题均可使用。
- [ ] 文件树、标签页和编辑器在窄屏设备上可操作。
- [ ] 所有操作有加载、成功、失败和只读状态反馈。
- [ ] 未保存编辑离开页面时不会静默丢失。
- [ ] zh-CN 与 en-US 的新增 i18n key 结构一致。

## 15. 已确认产品决策

| 决策         | 已确认方案                                                              |
| ------------ | ----------------------------------------------------------------------- |
| 导航入口     | 放在 Sidebar“更多”分组                                                  |
| 原始配置读取 | root Dashboard session 允许读取 `cmd_config.json` 和 `config/` 原始内容 |
| 受保护删除   | 允许在 `filesystem.manage` 与一次性 step-up 后执行                      |
| 上传         | Phase 2 提供                                                            |
| 初始限制     | 文本编辑 1 MiB；目录首屏 200 项；单文件上传 32 MiB；单次上传 64 MiB     |
| 隐藏项       | 显示所有以点号开头的文件和目录                                          |
| `plugins/`   | 默认只读；在 `filesystem.manage` 与 step-up 后可写                      |
| 配置保存     | 核心配置自动走验证、持久化和关联运行时 reload；插件配置走其现有配置服务 |
| 文件名搜索   | Phase 2 提供递归文件名搜索，不搜索内容                                  |

## 16. 参考实现与规范

- [项目架构](/dev/architecture)
- [Dashboard OpenAPI 开发说明](/dev/openapi)
- `dashboard/src/components/extension/SkillsSection.vue`
- `dashboard/src/utils/monacoLoader.ts`
- `astrbot/dashboard/api/skills.py`
- `astrbot/dashboard/services/skills_service.py`
- `astrbot/core/utils/astrbot_path.py`

外部方案调研结论：Monaco 适合作为浏览器内文本编辑器；code-server/OpenVSCode Server 是带服务端文件系统和终端的完整远程 IDE。当前需求只需要文件管理和语法高亮，因此不应承担完整远程 IDE 的认证、WebSocket、终端隔离和独立进程运维成本。
