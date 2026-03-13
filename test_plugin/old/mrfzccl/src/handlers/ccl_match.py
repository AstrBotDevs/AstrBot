from __future__ import annotations

import time
from typing import Any, AsyncIterator

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent

from ..tool import generate_image_or_fallback, generate_match_leaderboard_text

async def handle_match_help(self, event: AstrMessageEvent) -> AsyncIterator[Any]:
    """比赛模式帮助"""
    if event.get_group_id() is None:
        yield event.plain_result("请在群聊使用")
        return
    yield event.plain_result(
        """📋 比赛模式指令帮助
━━━━━━━━━━━━━━
/ccl 比赛创建 [名称] [题目限制] [时间限制(分钟)] - 创建比赛(仅管理员)
/ccl 比赛开始        - 开始比赛(仅管理员)
/ccl 比赛结束/结束比赛 - 结束比赛(仅管理员)
/ccl 比赛排行/排行   - 查看比赛排行榜
━━━━━━━━━━━━━━"""
    )

async def handle_match_create(
    self,
    event: AstrMessageEvent,
    name: str = "",
    question_limit: int = 0,
    time_limit: int = 0,
) -> AsyncIterator[Any]:
    """创建比赛（仅管理员）用法: /ccl 比赛创建 [名称] [题目限制] [时间限制(分钟)]"""
    group_id_raw = event.get_group_id()
    if group_id_raw is None:
        yield event.plain_result("请在群聊使用")
        return
    group_id = str(group_id_raw)
    sender_id = str(event.get_sender_id())

    # 检查管理员权限
    if self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
        yield event.plain_result("❌ 只有管理员可以创建比赛")
        return

    # 检查是否已有进行中的比赛
    existing = await self.match_repo.get_active_match(group_id)
    if existing:
        yield event.plain_result("❌ 当前群已有进行中的比赛")
        return

    # 设置题目限制和时间限制
    q_limit = question_limit if question_limit >= 0 else self.match_question_limit
    t_limit = time_limit if time_limit >= 0 else self.match_time_limit

    if q_limit < 0 or t_limit < 0:
        yield event.plain_result(f"参数未通过检验,q_limit:{q_limit},t_limit:{t_limit}")
        return

    # 创建比赛名称
    match_name = name if name else f"比赛_{int(time.time())}"
    # 创建比赛
    await self.match_repo.create_match(group_id, match_name, q_limit, t_limit)

    # 构建响应信息
    info = f"✅ 比赛「{match_name}」已创建！"
    if q_limit > 0:
        info += f"\n📝 题目限制: {q_limit}题"
    if t_limit > 0:
        info += f"\n⏱️ 时间限制: {t_limit}分钟"
    info += "\n进行答题即可参与比赛"
    yield event.plain_result(info)

async def match_start_precheck(self, event: AstrMessageEvent) -> tuple[bool, str | None, Any | None]:
    """`/ccl 比赛开始` 的锁外校验与 DB 状态更新。"""
    group_id_raw = event.get_group_id()
    if group_id_raw is None:
        return False, None, event.plain_result("请在群聊使用")

    sender_id = str(event.get_sender_id())
    group_id = str(group_id_raw)
    self.match_sessions[group_id] = event.unified_msg_origin

    # 检查管理员权限
    if self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
        return False, group_id, event.plain_result("❌ 只有管理员可以开始比赛")

    # 获取活跃比赛
    match = await self.match_repo.get_active_match(group_id)
    if not match:
        return False, group_id, event.plain_result("❌ 当前没有进行中的比赛")

    # 开始比赛
    await self.match_repo.start_match(match.match_id)

    return True, group_id, None

async def match_start_inlock(self, group_id: str) -> bytes | str | None:
    """`/ccl 比赛开始` 的锁内状态清理 + 出题逻辑。"""
    # 防止上次比赛残留题目导致 fc_init 返回 already_exists
    self.end_game(group_id)

    # 取消旧的比赛循环/提示任务（防止重复启动）
    if group_id in self.match_next_task:
        self._safe_cancel_task(self.match_next_task.pop(group_id, None))
    if group_id in self.match_loop_task:
        self._safe_cancel_task(self.match_loop_task.pop(group_id, None))
    self.match_question_state.pop(group_id, None)

    # 初始化第一题
    result = await self.fc_init(group_id)
    if result and result != "already_exists":
        self.match_question_state[group_id] = time.time()
        self._schedule_match_hint(group_id)

    return result

def build_match_start_response(event: AstrMessageEvent, result: bytes | str | None) -> Any:
    if result and result != "already_exists":
        return event.chain_result(
            [
                Comp.Plain("🏁 比赛已开始！答题即为参与比赛\n干员立绘,请使用/fcc [干员名称] 进行猜测"),
                Comp.Image.fromBytes(result),
            ]
        )
    return event.plain_result("🏁 比赛已开始！第一题获取失败，请重试")

async def match_end_precheck(self, event: AstrMessageEvent) -> tuple[bool, str | None, Any | None]:
    """`/ccl 比赛结束` 的锁外校验。"""
    group_id_raw = event.get_group_id()
    if group_id_raw is None:
        return False, None, event.plain_result("请在群聊使用")

    sender_id = str(event.get_sender_id())
    group_id = str(group_id_raw)

    # 检查管理员权限
    if self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
        return False, group_id, event.plain_result("❌ 只有管理员可以结束比赛")

    return True, group_id, None

async def match_end_inlock(self, group_id: str) -> tuple[bool, str, list]:
    """`/ccl 比赛结束` 的锁内结算逻辑。"""
    # 重新获取活跃比赛，避免与自动结束并发导致重复荣誉
    match_now = await self.match_repo.get_active_match(group_id)
    if not match_now or not match_now.is_active:
        return False, "", []

    match_name, _, top_participants = await self._end_match_and_collect_top(group_id, match_now)
    return True, match_name, top_participants

async def iter_match_end_results(
    self,
    event: AstrMessageEvent,
    match_name: str,
    top_participants: list,
) -> AsyncIterator[Any]:
    """`/ccl 比赛结束` 的锁外输出（图片优先，失败回退文本）。"""
    async for result in generate_image_or_fallback(
        event=event,
        generate_image_func=lambda: self.renderer.generate_match_leaderboard_image(
            match_name,
            top_participants,
            title=f"比赛「{match_name}」已结束排行榜",
        ),
        generate_text_func=lambda: generate_match_leaderboard_text(match_name, top_participants, ended=True),
    ):
        yield result

async def handle_match_leaderboard(self, event: AstrMessageEvent) -> AsyncIterator[Any]:
    """使用`/ccl 比赛排行`获取比赛排行榜"""
    group_id_raw = event.get_group_id()
    if group_id_raw is None:
        yield event.plain_result("请在群聊使用")
        return
    group_id = str(group_id_raw)

    # 获取活跃比赛
    match = await self.match_repo.get_active_match(group_id)
    if not match:
        yield event.plain_result("❌ 无进行中比赛")
        return

    # 获取参赛者列表并排序
    participants = await self.match_repo.get_participants(match.match_id)
    participants.sort(key=lambda p: p.score, reverse=True)

    top_participants = participants[:10]

    async for result in generate_image_or_fallback(
        event=event,
        generate_image_func=lambda: self.renderer.generate_match_leaderboard_image(
            match.match_name,
            top_participants,
        ),
        generate_text_func=lambda: generate_match_leaderboard_text(match.match_name, top_participants),
    ):
        yield result
