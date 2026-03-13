from __future__ import annotations

from typing import Any, AsyncIterator

from astrbot.api.event import AstrMessageEvent

from ..tool import (
    generate_correct_leaderboard_text,
    generate_hints_leaderboard_text,
    generate_image_or_fallback,
    generate_user_profile_text,
    generate_wrong_leaderboard_text,
)

async def handle_correct_answers_leaderboard(self, event: AstrMessageEvent) -> AsyncIterator[Any]:
    """获取正确个数的排行榜命令 /ccl 排行榜"""
    if self.require_admin:
        sender_id = str(event.get_sender_id())
        # 检查管理员权限
        if self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
            yield event.plain_result("❌ 只有管理员可以查看排行榜")
            return

    try:
        # 获取排行榜数据（前10名）
        users = await self.user_qna_repo.get_correct_answers_leaderboard(limit=10)

        if not users:
            yield event.plain_result("📊 当前还没有用户的答题记录哦~")
            return

        # 获取统计信息
        summary = await self.user_qna_repo.get_leaderboard_summary()

        # 使用统一的图片/文本生成函数
        async for result in generate_image_or_fallback(
            event=event,
            generate_image_func=lambda: self.renderer.generate_correct_leaderboard_image(users),
            generate_text_func=lambda: generate_correct_leaderboard_text(users, summary),
        ):
            yield result

    except Exception as e:
        yield event.plain_result(f"获取排行榜时出现错误: {str(e)}")

async def handle_wrong_answers_leaderboard(self, event: AstrMessageEvent) -> AsyncIterator[Any]:
    """获取错误个数的排行榜命令 /ccl 错误排行榜"""
    if self.require_admin:
        sender_id = str(event.get_sender_id())
        # 检查管理员权限
        if self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
            yield event.plain_result("❌ 只有管理员可以查看排行榜")
            return

    try:
        # 获取排行榜数据（前10名）
        users = await self.user_qna_repo.get_wrong_answers_leaderboard(limit=10)

        if not users:
            yield event.plain_result("📊 当前还没有用户的答题记录哦~")
            return

        # 使用统一的图片/文本生成函数
        async for result in generate_image_or_fallback(
            event=event,
            generate_image_func=lambda: self.renderer.generate_wrong_leaderboard_image(users),
            generate_text_func=lambda: generate_wrong_leaderboard_text(users),
        ):
            yield result

    except Exception as e:
        yield event.plain_result(f"获取排行榜时出现错误: {str(e)}")

async def handle_hints_usage_leaderboard(self, event: AstrMessageEvent) -> AsyncIterator[Any]:
    """获取使用提示次数的排行榜命令 /ccl 提示排行榜"""
    if self.require_admin:
        sender_id = str(event.get_sender_id())
        # 检查管理员权限
        if self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
            yield event.plain_result("❌ 只有管理员可以查看排行榜")
            return

    try:
        # 获取排行榜数据（前10名）
        users = await self.user_qna_repo.get_hints_usage_leaderboard(limit=10)

        if not users:
            yield event.plain_result("📊 当前还没有用户的答题记录哦~")
            return

        # 使用统一的图片/文本生成函数
        async for result in generate_image_or_fallback(
            event=event,
            generate_image_func=lambda: self.renderer.generate_hints_leaderboard_image(users),
            generate_text_func=lambda: generate_hints_leaderboard_text(users),
        ):
            yield result

    except Exception as e:
        yield event.plain_result(f"获取排行榜时出现错误: {str(e)}")

async def handle_user_profile_retrieval(
    self,
    event: AstrMessageEvent,
    user_id: str | None = None,
) -> AsyncIterator[Any]:
    """获取个人信息获取 /ccl 名片 [user_id] (如果user_id为空默认为发送人)"""
    try:
        # 确定用户ID
        target_user_id = user_id or event.get_sender_id()

        # 获取用户信息及排名
        user_stats, rank_info = await self.user_qna_repo.get_user_profile_with_rank(target_user_id)

        # 获取用户荣誉
        honors = await self.match_repo.get_user_honors(str(target_user_id))

        # 没有任何记录时直接返回
        if not user_stats and not honors:
            yield event.plain_result("❌ 未找到该用户的答题记录")
            return

        # 没有答题记录但有荣誉：直接用文本输出（名片图片依赖 user_stats）
        if not user_stats:
            yield event.plain_result(generate_user_profile_text(user_stats, rank_info, honors, str(target_user_id)))
            return

        # 使用统一的图片/文本生成函数
        async for result in generate_image_or_fallback(
            event=event,
            generate_image_func=lambda: self.renderer.generate_user_profile_image(user_stats, rank_info, honors),
            generate_text_func=lambda: generate_user_profile_text(user_stats, rank_info, honors, str(target_user_id)),
        ):
            yield result

    except Exception as e:
        yield event.plain_result(f"获取用户信息时出现错误: {str(e)}")
