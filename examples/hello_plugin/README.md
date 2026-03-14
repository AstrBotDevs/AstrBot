# Hello Plugin

这是给 AstrBot SDK 插件作者准备的最小示例。

## 目录结构

```text
hello_plugin/
├── plugin.yaml
├── requirements.txt
├── main.py
└── tests
    └── test_plugin.py
```

## 能学到什么

- 如何定义一个 `Star` 插件
- 如何注册命令 handler
- 如何使用 `MessageEvent.reply()`
- 如何从 `Context` 里读取当前插件元数据
- 如何用 `MockContext` / `MockMessageEvent` 写插件测试

## 运行

在仓库根目录执行：

```bash
astrbot-sdk validate --plugin-dir examples/hello_plugin
astrbot-sdk dev --local --plugin-dir examples/hello_plugin --event-text hello
astrbot-sdk dev --local --watch --plugin-dir examples/hello_plugin --event-text hello
```

## 测试

```bash
python -m pytest examples/hello_plugin/tests/test_plugin.py -v
```

## 代码说明

- `hello`: 最小命令，收到 `hello` 时回复 `Hello, World!`
- `about`: 读取 `ctx.metadata.get_current_plugin()`，演示 capability 客户端的基础用法
