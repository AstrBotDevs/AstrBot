# QQOfficial 模块修复 - 产品需求文档

## Overview
- **Summary**: 修复 QQOfficial 模块中的多个 bug，包括文本分块逻辑、流式消息降级条件、频道消息图片发送和消息回复限流器等问题
- **Purpose**: 解决 PR #7176 中提出的代码审查问题，确保 QQOfficial 模块的稳定性和可靠性
- **Target Users**: 开发团队和使用 QQOfficial 模块的用户

## Goals
- 修复 chunk_text 函数的游标更新逻辑，避免死循环和重复块风险
- 完善流式 C2C 降级条件，覆盖所有富媒体类型
- 修复频道消息图片发送问题，支持 URL 图片
- 改进 MessageReplyLimiter 的日志记录和并发安全性
- 清理未使用的上传辅助函数和缓存

## Non-Goals (Out of Scope)
- 重构整个 QQOfficial 模块
- 添加新功能或特性
- 修改其他平台适配器的代码

## Background & Context
- PR #7176 提出了多个代码审查问题，需要修复
- 参考 OpenClaw 项目的实现方式进行修复
- 确保修复后的代码与现有代码风格和架构保持一致

## Functional Requirements
- **FR-1**: 修复 chunk_text 函数的游标更新逻辑，确保每次循环 start 都单调前进
- **FR-2**: 完善流式 C2C 降级条件，当检测到任何富媒体时都降级为非流式发送
- **FR-3**: 修复频道消息图片发送问题，支持 URL 图片
- **FR-4**: 改进 MessageReplyLimiter，使用 logger 进行日志记录，避免使用模块级全局变量
- **FR-5**: 清理未使用的上传辅助函数和缓存

## Non-Functional Requirements
- **NFR-1**: 代码质量：修复后的代码应符合项目的代码风格和最佳实践
- **NFR-2**: 安全性：确保 MessageReplyLimiter 的并发安全性
- **NFR-3**: 可维护性：清理未使用的代码，提高代码可读性

## Constraints
- **Technical**: 保持与现有代码架构的一致性
- **Dependencies**: 参考 OpenClaw 项目的实现方式

## Assumptions
- OpenClaw 项目的实现方式是可靠的参考
- 修复后的代码应通过项目的测试和 lint 检查

## Acceptance Criteria

### AC-1: 修复 chunk_text 函数
- **Given**: 长文本需要分块
- **When**: 调用 chunk_text 函数
- **Then**: 函数应正确分块，无死循环，无重复块
- **Verification**: `programmatic`
- **Notes**: 确保每次循环 start 都单调前进

### AC-2: 完善流式 C2C 降级条件
- **Given**: 发送包含语音、视频或文件的流式 C2C 消息
- **When**: 触发流式消息发送
- **Then**: 应降级为非流式发送
- **Verification**: `programmatic`
- **Notes**: 确保所有富媒体类型都被覆盖

### AC-3: 修复频道消息图片发送
- **Given**: 发送包含 URL 图片的频道消息
- **When**: 调用频道消息发送接口
- **Then**: 应正确发送 URL 图片
- **Verification**: `programmatic`
- **Notes**: 区分本地路径和 URL 图片的处理

### AC-4: 改进 MessageReplyLimiter
- **Given**: 使用 MessageReplyLimiter 进行消息回复限流
- **When**: 记录消息回复或检查限流
- **Then**: 应使用 logger 进行日志记录，且线程安全
- **Verification**: `programmatic`
- **Notes**: 避免使用模块级全局变量

### AC-5: 清理未使用的代码
- **Given**: 检查上传相关代码
- **When**: 分析代码使用情况
- **Then**: 移除或标记未使用的上传辅助函数和缓存
- **Verification**: `human-judgment`
- **Notes**: 保持代码整洁

## Open Questions
- [ ] 是否需要添加单元测试来验证修复效果？
- [ ] 清理未使用代码时是否需要保留某些接口以保持向后兼容？