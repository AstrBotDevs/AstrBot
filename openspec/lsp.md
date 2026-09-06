# LSP (Language Server Protocol) 协议规范

## 概述

LSP（Language Server Protocol）是由 Microsoft 制定的开放协议，用于在编辑器/IDE 与语言智能服务之间提供语言特性支持。

**核心问题**：传统上，为编辑器提供编程语言支持（如自动完成、跳转到定义）需要针对每个编辑器/IDE 单独实现。例如，Eclipse CDT 插件用 Java 编写，VS Code 扩展用 TypeScript 编写，C# 支持用 C# 编写。

**解决方案**：语言服务器在其自己的进程中运行，编辑器通过标准协议与之通信。只需实现一次语言服务器，即可集成到任何支持 LSP 的工具中。

## 实现状态

| 组件 | 状态 | 说明 |
|------|------|------|
| LSP Client | ❌ 不计划 | AstrBot 不作为 LSP 客户端使用（用于 IDE 集成） |
| LSP Server | ❌ 不计划 | 作为 AI 编程助手，暂无语言服务器需求 |
| 参考文档 | ✅ 完成 | 本文档为 LSP 协议参考，不做实现 |

> 相关协议: [A2A](a2a.md)（Agent 间通信）, [agent-message](agent-message.md)（消息处理框架）

**参考**：[Language Server Protocol](https://microsoft.github.io/language-server-protocol/) by Microsoft

## 设计哲学

### 抽象层级

LSP 成功的原因在于其**编辑器级别**的抽象，而非编程语言领域模型级别：

| 层级 | LSP 抽象 | 传统方法 |
|------|----------|----------|
| 编辑器级别 | 文本文档 URI、光标位置 | ✓ |
| 语言模型级别 | 抽象语法树、编译器符号 | ✗ |

**简化协议**：标准化文本文档 URI 或光标位置，比标准化抽象语法树和编译器符号简单得多。

### 进程隔离

```
┌─────────────────────────────────────┐
│           编辑器/IDE                │
│  - 文档状态管理                    │
│  - 用户交互                        │
│  - UI 渲染                         │
└─────────────────────────────────────┘
                      │ JSON-RPC 2.0
                      ▼
┌─────────────────────────────────────┐
│         语言服务器 (独立进程)        │
│  - 词法分析                        │
│  - 语法分析                        │
│  - 类型检查                        │
│  - 代码生成                         │
└─────────────────────────────────────┘
```

**优势**：
- 避免与单个进程模型相关的性能问题
- 语言服务器可用任何语言实现（Python、Go、JavaScript 等）
- 服务器崩溃不影响编辑器

## 架构

### 通信流程

```
┌─────────────────────────────────────┐
│           编辑器/IDE (LSP 客户端)    │
└─────────────────────────────────────┘
                      │ JSON-RPC 2.0
                      ▼
┌─────────────────────────────────────┐
│         LSP 服务器 (独立进程)        │
│  - 代码补全                         │
│  - 诊断（错误、警告）               │
│  - 悬停信息                         │
│  - 跳转到定义                       │
│  - 重构支持                         │
└─────────────────────────────────────┘
```

### 传输方式

| 传输方式 | 说明 |
|----------|------|
| **stdio** | 通过 stdin/stdout 通信（常用） |
| **Socket** | TCP 套接字 |
| **Named Pipes** | 命名管道 |
| **Node IPC** | Node.js 进程间通信 |

## 会话流程

### 1. 打开文档

```
编辑器 → 服务器：textDocument/didOpen
内容：{
  "textDocument": {
    "uri": "file:///path/to/file.py",
    "languageId": "python",
    "version": 1,
    "text": "print('hello')"
  }
}
```

服务器将文档内容加载到内存，不再依赖文件系统。

### 2. 编辑文档

```
编辑器 → 服务器：textDocument/didChange
内容：{ "textDocument": {...}, "contentChanges": [...] }
```

服务器更新内存中的文档状态，分析语义信息。

### 3. 发布诊断

```
服务器 → 编辑器：textDocument/publishDiagnostics
内容：{ "uri": "...", "diagnostics": [...] }
```

服务器通知编辑器检测到的错误和警告。

### 4. 跳转到定义

```
编辑器 → 服务器：textDocument/definition
内容：{
  "textDocument": { "uri": "file:///path/to/file.py" },
  "position": { "line": 3, "character": 12 }
}

服务器 → 编辑器：响应
内容：{
  "uri": "file:///path/to/definition.py",
  "range": { "start": {...}, "end": {...} }
}
```

### 5. 关闭文档

```
编辑器 → 服务器：textDocument/didClose
内容：{ "textDocument": { "uri": "..." } }
```

服务器释放文档内存，当前内容与文件系统同步。

## 消息格式

所有消息均为 JSON-RPC 2.0：

### 请求

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "textDocument/definition",
  "params": {
    "textDocument": {
      "uri": "file:///path/to/file.py"
    },
    "position": {
      "line": 3,
      "character": 12
    }
  }
}
```

### 响应

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "uri": "file:///path/to/definition.py",
    "range": {
      "start": { "line": 0, "character": 4 },
      "end": { "line": 0, "character": 11 }
    }
  }
}
```

### 通知

```json
{
  "jsonrpc": "2.0",
  "method": "textDocument/didOpen",
  "params": {
    "textDocument": {
      "uri": "file:///path/to/file",
      "languageId": "python",
      "version": 1,
      "text": "print('hello')"
    }
  }
}
```

### 错误

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32600,
    "message": "Invalid Request"
  }
}
```

## 核心方法

### 生命周期

| 方法 | 方向 | 描述 |
|------|------|------|
| `initialize` | C→S | 初始化连接，交换能力 |
| `initialized` | C→S | 客户端通知服务器初始化完成 |
| `shutdown` | C→S | 请求服务器关闭 |
| `exit` | C→S | 退出会话 |

### 文本文档同步

| 方法 | 方向 | 描述 |
|------|------|------|
| `textDocument/didOpen` | C→S | 文档被打开 |
| `textDocument/didChange` | C→S | 文档内容变更 |
| `textDocument/didClose` | C→S | 文档被关闭 |
| `textDocument/didSave` | C→S | 文档被保存 |

### 代码补全

| 方法 | 方向 | 描述 |
|------|------|------|
| `textDocument/completion` | C→S | 请求代码补全 |
| `completionItem/resolve` | C→S | 解析补全项详情 |

### 导航

| 方法 | 方向 | 描述 |
|------|------|------|
| `textDocument/hover` | C→S | 获取悬停信息 |
| `textDocument/definition` | C→S | 跳转到定义 |
| `textDocument/typeDefinition` | C→S | 跳转到类型定义 |
| `textDocument/implementation` | C→S | 跳转到实现 |
| `textDocument/references` | C→S | 查找引用 |
| `textDocument/documentSymbol` | C→S | 文档符号 |
| `textDocument/workspaceSymbol` | C→S | 工作区符号搜索 |

### 代码诊断

| 方法 | 方向 | 描述 |
|------|------|------|
| `textDocument/publishDiagnostics` | S→C | 服务器发布诊断信息 |

### 代码操作

| 方法 | 方向 | 描述 |
|------|------|------|
| `textDocument/codeAction` | C→S | 代码动作/修复 |
| `textDocument/rename` | C→S | 重命名符号 |
| `textDocument/formatting` | C→S | 文档格式化 |
| `textDocument/rangeFormatting` | C→S | 范围格式化 |

## 能力 (Capabilities)

### 服务器能力声明

```json
{
  "capabilities": {
    "textDocumentSync": 2,
    "completionProvider": {
      "resolveProvider": true,
      "triggerCharacters": [".", "("]
    },
    "hoverProvider": true,
    "definitionProvider": true,
    "typeDefinitionProvider": true,
    "implementationProvider": true,
    "referencesProvider": true,
    "documentSymbolProvider": true,
    "workspaceSymbolProvider": true,
    "codeActionProvider": true,
    "renameProvider": true,
    "documentFormattingProvider": true,
    "diagnosticProvider": {
      "interFileDependencies": false,
      "workspaceDiagnostics": false
    }
  }
}
```

### 客户端能力声明

```json
{
  "capabilities": {
    "workspace": {
      "applyEdit": true,
      "workspaceFolders": true,
      "fileOperations": {
        "willRename": true
      }
    },
    "textDocument": {
      "synchronization": {
        "willSave": true,
        "willSaveWaitUntil": true,
        "didSave": true
      },
      "completion": {
        "completionItem": {
          "snippetSupport": true,
          "documentationFormat": ["markdown", "plaintext"]
        }
      },
      "hover": {
        "contentFormat": ["markdown", "plaintext"]
      }
    }
  }
}
```

### 能力协商

服务器声明支持的功能，客户端声明支持的功能。双方只使用都支持的功能。

## 错误码

| 码值 | 名称 | 描述 |
|------|------|------|
| -32700 | Parse Error | 无效的 JSON |
| -32600 | Invalid Request | 格式错误的请求 |
| -32601 | Method Not Found | 未知方法 |
| -32602 | Invalid Params | 无效参数 |
| -32603 | Internal Error | 服务器内部错误 |
| -32099 | Server Not Initialized | 服务器未初始化 |
| -32000 | Unknown Error | 未知错误 |

## 数据类型

### TextDocumentItem

```json
{
  "uri": "file:///path/to/file",
  "languageId": "python",
  "version": 1,
  "text": "print('hello')"
}
```

### Position

```json
{
  "line": 3,
  "character": 12
}
```

### Range

```json
{
  "start": { "line": 0, "character": 4 },
  "end": { "line": 0, "character": 11 }
}
```

### Location

```json
{
  "uri": "file:///path/to/file",
  "range": { "start": {...}, "end": {...} }
}
```

### Diagnostic

```json
{
  "range": { "start": {...}, "end": {...} },
  "severity": 1,
  "code": "E001",
  "source": "pylint",
  "message": "Undefined variable 'x'"
}
```

## 实现注意事项

- LSP 服务器在其自己的进程中运行，避免性能问题
- 使用 Content-Length 头解析 JSON-RPC 消息
- 支持增量文档同步（textDocumentSync）
- 诊断信息通过 `textDocument/publishDiagnostics` 推送
- 服务器应保持运行，避免每次编辑都重启进程
- 客户端和服务器通过能力声明协商支持的功能
- 文档内容由客户端管理，服务器无需直接访问文件系统
