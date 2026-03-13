from __future__ import annotations

from typing import Any, AsyncIterator

from astrbot.api.event import AstrMessageEvent


async def handle_reset_user_data(
    self,
    event: AstrMessageEvent,
    target_user_id: str = "",
) -> AsyncIterator[Any]:
    """清除用户答题数据（仅管理员）/ccl 清除数据 [user_id]"""
    sender_id = str(event.get_sender_id())

    # 检查管理员权限
    if self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
        yield event.plain_result("❌ 只有管理员可以清除数据")
        return

    if target_user_id:
        await self.user_qna_repo.reset_user_stats(target_user_id)
        yield event.plain_result(f"✅ 用户 {target_user_id} 的答题数据已清除")
    else:
        await self.user_qna_repo.reset_user_stats(sender_id)
        yield event.plain_result("✅ 您的答题数据已清除")


async def handle_reset_user_honors_cmd(
    self,
    event: AstrMessageEvent,
    target_user_id: str = "",
) -> AsyncIterator[Any]:
    """清除用户荣誉数据（仅管理员）/ccl 清除荣誉 [user_id]"""
    sender_id = str(event.get_sender_id())

    # 检查管理员权限
    if self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
        yield event.plain_result("❌ 只有管理员可以清除荣誉")
        return

    if target_user_id:
        await self.match_repo.reset_user_honors(target_user_id)
        yield event.plain_result(f"✅ 用户 {target_user_id} 的荣誉数据已清除")
    else:
        await self.match_repo.reset_user_honors(sender_id)
        yield event.plain_result("✅ 您的荣誉数据已清除")


async def handle_reset_all_data_cmd(self, event: AstrMessageEvent) -> AsyncIterator[Any]:
    """清除所有用户的答题数据（仅管理员）/ccl 清除所有数据"""
    sender_id = str(event.get_sender_id())

    # 检查管理员权限
    if self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
        yield event.plain_result("❌ 只有管理员可以清除所有数据")
        return

    await self.user_qna_repo.reset_all_stats()
    yield event.plain_result("✅ 所有用户的答题数据已清除")


async def handle_reset_all_honors_cmd(self, event: AstrMessageEvent) -> AsyncIterator[Any]:
    """清除所有用户的荣誉数据（仅管理员）/ccl 清除所有荣誉"""
    sender_id = str(event.get_sender_id())

    # 检查管理员权限
    if self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
        yield event.plain_result("❌ 只有管理员可以清除所有荣誉")
        return

    await self.match_repo.reset_all_honors()
    yield event.plain_result("✅ 所有用户的荣誉数据已清除")


async def handle_grant_honor_cmd(
    self,
    event: AstrMessageEvent,
    target_user_id: str = "",
    rank: int = 1,
    match_name: str = "",
    correct_count: int = 0,
) -> AsyncIterator[Any]:
    """授予用户特定荣誉（仅管理员）/ccl 授予荣誉 [user_id] [名次] [比赛名称] [答对数量]"""
    sender_id = str(event.get_sender_id())

    # 检查管理员权限
    if self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
        yield event.plain_result("❌ 只有管理员可以授予荣誉")
        return

    # 检查参数完整性
    if not target_user_id or not match_name:
        yield event.plain_result("❌ 请提供完整参数: /ccl 授予荣誉 [user_id] [名次] [比赛名称] [答对数量]")
        return

    # 根据名次生成奖牌表情
    if rank == 1:
        medal = "🥇"
    elif rank == 2:
        medal = "🥈"
    elif rank == 3:
        medal = "🥉"
    else:
        medal = f"{rank}"

    # 计算得分（错误数默认为0）
    score = correct_count - 0

    # 保存荣誉
    await self.match_repo.save_honor(
        user_id=target_user_id,
        match_id=0,  # 虚拟比赛ID
        match_name=match_name,
        rank=rank,
        correct_count=correct_count,
        wrong_count=0,
        score=score,
    )

    yield event.plain_result(
        f"✅ 已授予用户 {target_user_id} 荣誉: {medal} {match_name} 第{rank}名, 答对{correct_count}题"
    )
