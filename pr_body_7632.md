### 问题描述
`send_message_to_user` 发送文件时，传入相对路径（如 `filename.md`）会先尝试绝对路径失败，再试绝对路径才成功，浪费 token。

### 修复方案
在 `_resolve_path_from_sandbox` 方法中，当 path 是相对路径时，先尝试解析到 workspace 目录下检查文件是否存在。同时添加了 path 安全检查，防止 `..` 等路径遍历问题。

### Related Issue
Fixes #7632

## Summary by Sourcery

Bug Fixes:
- Ensure non-absolute paths in send_message_to_user are resolved relative to the active workspace when possible instead of relying solely on the raw filesystem path.