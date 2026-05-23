# QQOfficial 模块修复 - 实现计划

## [x] 任务 1: 修复 chunk_text 函数的游标更新逻辑
- **优先级**: P0
- **依赖**: 无
- **描述**: 
  - 修改 qqofficial_message_event.py 中的 chunk_text 函数
  - 简化游标更新逻辑，确保每次循环 start 都单调前进
  - 避免使用复杂的 overlap 逻辑和 find 方法
- **接受标准**: AC-1
- **测试需求**:
  - `programmatic` TR-1.1: 测试长文本分块功能，确保无死循环和重复块
  - `programmatic` TR-1.2: 测试边界条件，如文本长度正好等于限制、小于限制等
- **注意**: 参考 PR 中的建议，使用 `start = max(breakpoint - overlap, start + 1)` 或类似逻辑

## [x] 任务 2: 完善流式 C2C 降级条件
- **优先级**: P0
- **依赖**: 无
- **描述**: 
  - 修改 qqofficial_message_event.py 中的流式消息降级逻辑
  - 确保当检测到任何富媒体时都降级为非流式发送
  - 覆盖图片、语音、视频和文件等所有富媒体类型
- **接受标准**: AC-2
- **测试需求**:
  - `programmatic` TR-2.1: 测试包含语音的流式 C2C 消息，应降级为非流式
  - `programmatic` TR-2.2: 测试包含视频的流式 C2C 消息，应降级为非流式
  - `programmatic` TR-2.3: 测试包含文件的流式 C2C 消息，应降级为非流式
- **注意**: 参考 PR 中的建议，使用 `if stream and (image_source or record_file_path or video_file_source or file_source):`

## [x] 任务 3: 修复频道消息图片发送问题
- **优先级**: P0
- **依赖**: 无
- **描述**: 
  - 修改 qqofficial_platform_adapter.py 中的频道消息发送逻辑
  - 支持 URL 图片的发送
  - 区分本地路径和 URL 图片的处理
- **接受标准**: AC-3
- **测试需求**:
  - `programmatic` TR-3.1: 测试发送包含 URL 图片的频道消息
  - `programmatic` TR-3.2: 测试发送包含本地路径图片的频道消息
- **注意**: 参考 PR 中的建议，添加对 URL 图片的特殊处理

## [x] 任务 4: 改进 MessageReplyLimiter
- **优先级**: P1
- **依赖**: 无
- **描述**: 
  - 修改 rate_limiter.py 中的 MessageReplyLimiter 类
  - 使用 logger 进行日志记录，替代 print
  - 改进并发安全性，避免使用模块级全局变量
- **接受标准**: AC-4
- **测试需求**:
  - `programmatic` TR-4.1: 测试消息回复限流功能
  - `programmatic` TR-4.2: 测试并发场景下的限流器行为
- **注意**: 参考 OpenClaw 项目的实现方式

## [x] 任务 5: 清理未使用的上传辅助函数和缓存
- **优先级**: P2
- **依赖**: 无
- **描述**: 
  - 检查 chunked_upload.py 中的上传相关代码
  - 移除或标记未使用的上传辅助函数和缓存
  - 保持代码整洁
- **接受标准**: AC-5
- **测试需求**:
  - `human-judgment` TR-5.1: 检查代码是否整洁，无未使用的函数和缓存
- **注意**: 确保不影响现有功能