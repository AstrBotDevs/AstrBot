# AstrBot插件：Markdown图片处理器

## 简介
这是一个 AstrBot 插件，用于监听 LLM 发出的每一条消息，移除其中的 Markdown 格式，并提取和发送消息中的图片。

## 功能
- ✅ 自动检测 LLM 回复中的 Markdown 格式并移除
- ✅ 提取 AI 回复中的图片链接（Markdown 格式：`![alt](url)`）
- ✅ 自动转换 Dify 容器内地址为真实可访问地址
- ✅ 下载并发送图片到聊天
- ✅ 完全兼容 `astrbot_plugin_markdown_killer` 的所有功能
- ✅ 可配置的功能开关（Markdown 移除、图片提取）
- ✅ 在控制台输出详细的处理日志

## 特性

### 1. Markdown 格式移除
- 移除代码块 ` ```code``` `
- 移除行内代码 `` `code` ``
- 移除粗体 `**text**` 和 `__text__`
- 移除斜体 `*text*` 和 `_text_`（智能识别，避免误删数学公式）
- 移除标题 `# heading`
- 移除引用 `> quote`
- 移除链接 `[text](url)`
- 移除列表标记 `- item` 和 `* item`
- 移除图片 `![alt](url)`

### 2. 图片处理
- 自动识别 Markdown 图片语法：`![描述](图片地址)`
- 支持 Dify 容器内相对路径转换：
  - 容器内地址：`/files/xxx/file-preview?...`
  - 转换为：`http://223.109.141.49:8081/files/xxx/file-preview?...`
- 自动下载图片并发送到聊天
- 支持完整 URL 和相对路径

## 安装

### 方法一：手动安装
1. 将本插件目录放置在 AstrBot 的 `data/plugins` 目录下
2. 确保 `metadata.yaml` 配置正确
3. 编辑 `config.yaml` 配置 Dify 服务器地址
4. 重启 AstrBot 或重载插件

### 方法二：依赖安装
确保安装了以下依赖：
```bash
pip install httpx
```

## 配置

编辑 `config.yaml` 文件：

```yaml
# Dify 服务器地址配置
dify_host: "http://223.109.141.49:8081"

# 是否启用 Markdown 格式移除功能
enable_markdown_removal: true

# 是否启用图片提取和发送功能
enable_image_extraction: true
```

### 配置说明

- `dify_host`: Dify 服务器的真实访问地址，用于将容器内的相对路径转换为可访问的完整 URL
- `enable_markdown_removal`: 是否启用 Markdown 格式移除功能（默认：true）
- `enable_image_extraction`: 是否启用图片提取和发送功能（默认：true）

## 使用示例

### 输入（AI 回复）
```json
{
  "text": "守护2.0的登录方法很简单：  \n\n1. 打开守护2.0的登录页面  \n2. **输入账号和密码**  \n3. 点击登录按钮即可  \n\n**操作示例：**  \n![登录示例图](/files/b5dda75c-0a48-4d13-b6d7-63107d02067f/file-preview?timestamp=1764989761&nonce=1fe89a248f6ec9d4beef0423a18013d0&sign=qosMYTgXAIDd53Q-bo0igVNTNmfkx_X8w0-CiBpuvmg=)"
}
```

### 处理结果

1. **文本输出**（移除 Markdown）：
```
守护2.0的登录方法很简单：

1. 打开守护2.0的登录页面
2. 输入账号和密码
3. 点击登录按钮即可

操作示例：
登录示例图
```

2. **图片发送**：
- 自动下载图片：`http://223.109.141.49:8081/files/b5dda75c-0a48-4d13-b6d7-63107d02067f/file-preview?...`
- 发送到聊天

## 工作流程

1. 监听 LLM 回复事件
2. 提取文本中的所有图片链接（Markdown 格式）
3. 将 Dify 容器内地址转换为真实地址
4. 移除文本中的 Markdown 格式
5. 下载图片并发送到聊天
6. 输出处理日志

## 注意事项

- 插件会尝试智能区分 Markdown 斜体和数学公式，但在极少数复杂边缘情况下可能会有误判
- 图片下载超时时间为 30 秒
- 图片会保存到临时文件，发送后自动清理
- 如果图片下载失败，会在日志中输出错误信息，但不会影响文本消息的发送
- 确保 Dify 服务器地址配置正确，否则图片可能无法下载

## 兼容性

- ✅ 完全兼容 `astrbot_plugin_markdown_killer` 的所有功能
- ✅ 可以作为 `astrbot_plugin_markdown_killer` 的升级版本使用
- ✅ 支持 AstrBot 的消息链（MessageChain）和图片发送

## 日志示例

```
[Markdown Image Handler] 插件已加载
[Markdown Image Handler] Dify 服务器地址: http://223.109.141.49:8081
[Markdown Image Handler] Markdown 移除: 启用
[Markdown Image Handler] 图片提取: 启用
[Markdown Image Handler] 检测到 1 张图片
[Markdown Image Handler] 提取图片: 登录示例图 -> http://223.109.141.49:8081/files/xxx/file-preview?...
[Markdown Image Handler] 正在下载图片: http://223.109.141.49:8081/files/xxx/file-preview?...
[Markdown Image Handler] 图片发送成功: http://223.109.141.49:8081/files/xxx/file-preview?...
```

## 故障排除

### 图片无法下载
1. 检查 `config.yaml` 中的 `dify_host` 配置是否正确
2. 确认 Dify 服务器是否可访问
3. 检查图片 URL 中的签名是否过期

### 图片无法发送
1. 确认 AstrBot 的图片发送功能是否正常
2. 检查临时文件目录是否有写入权限
3. 查看日志中的错误信息

### Markdown 未被移除
1. 检查 `config.yaml` 中的 `enable_markdown_removal` 是否为 `true`
2. 查看日志确认插件是否正常加载

## 作者
yangyongjie

## 版本历史
- v1.0.0 (2025-12-06)
  - 初始版本
  - 实现 Markdown 格式移除功能
  - 实现图片提取和发送功能
  - 支持 Dify 容器地址转换
