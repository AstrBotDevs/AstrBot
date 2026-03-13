from __future__ import annotations

import time
import traceback
from difflib import SequenceMatcher
from typing import Any, AsyncIterator

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..tool import (
    calculate_char_coverage_set,
    check_daily_limit,
    check_homophone,
    generate_image_or_fallback,
    generate_match_leaderboard_text,
    has_active_game,
    resolve_alias,
)

async def handle_fc(
    self,
    event: AstrMessageEvent,
    *,
    user_id: str,
    sender_id: str,
    is_group: bool,
    group_id: str | None,
) -> Any | None:
    """Core logic for `/fc` (expects room lock is held by caller)."""
    response = None

    # 确保数据库初始化
    try:
        await self.db.init_db()
        logger.info("[Mrfzccl] 数据库初始化完成")
    except Exception as e:
        logger.error(f"[Mrfzccl] 数据库初始化失败: {e}")
        response = event.chain_result(
            [
                Comp.At(qq=sender_id),
                Comp.Plain(" 数据库初始化失败，请联系管理员"),
            ]
        )

    if response is None:
        # 检查是否在比赛模式和是否限制（仅群聊）
        match = await self.match_repo.get_active_match(group_id) if is_group else None
        # 非管理员进行次数检测
        if self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
            # 非比赛模式下检查每日限制
            if not match and not check_daily_limit(sender_id, self.daily_counter, self.daily_limit):
                response = event.plain_result(f"今日游戏次数已达上限({self.daily_limit}次)，请明天再来！")

    if response is None:
        try:
            # 调用初始化游戏方法
            result = await self.fc_init(user_id)
            if result == "already_exists":
                response = event.plain_result("已经初始化,请不要重复操作")
            elif result is None:
                response = event.plain_result("图片获取失败,请重试")
            else:
                # 发送游戏图片
                response = event.chain_result(
                    [
                        Comp.Plain("干员立绘,请使用/fcc [干员名称] 进行猜测"),
                        Comp.Image.fromBytes(result),
                    ]
                )
        except Exception as e:
            logger.error(f"[fc] 命令执行失败: {e}")
            logger.error(traceback.format_exc())
            response = event.plain_result("游戏初始化失败，请稍后重试")

    return response

async def handle_fcc(
    self,
    event: AstrMessageEvent,
    *,
    user_id: str,
    sender_id: str,
    is_group: bool,
    group_id: str | None,
) -> tuple[list[Any], tuple[str, list] | None]:
    """Core logic for `/fcc` (expects room lock is held by caller)."""
    responses: list[Any] = []
    match_end_payload: tuple[str, list] | None = None  # (ended_match_name, ended_top_participants)

    logger.debug(
        f"[fcc] user_id={user_id}, player_keys={list(self.player.keys())}, has_active={has_active_game(self.player, user_id)}"
    )

    # 检查是否有活跃比赛
    match = await self.match_repo.get_active_match(group_id) if is_group else None

    # 检查用户是否有活跃游戏
    if not has_active_game(self.player, user_id):
        if match:
            responses.append(event.plain_result("比赛期间请等待管理员发送题目"))
        else:
            responses.append(event.plain_result("没有初始化房间,请使用/fc"))
        return responses, match_end_payload

    # 提取并清理用户输入的猜测内容
    guess_text = self.extract_and_sanitize_input(event.message_str, "fcc")
    if not guess_text:
        responses.append(
            event.chain_result(
                [
                    Comp.At(qq=sender_id),
                    Comp.Plain(" 请输入要猜测的干员名称"),
                ]
            )
        )
        return responses, match_end_payload

    correct_name = self.player[user_id]["name"]  # 获取正确答案

    # 解析别名（将用户输入的别名转换为正式名称）
    resolved_guess = resolve_alias(guess_text, self.alias_map)

    # 计算相似度
    similarity = SequenceMatcher(None, correct_name, resolved_guess).ratio()
    # 计算字符覆盖率
    calculate = calculate_char_coverage_set(correct_name, resolved_guess)
    # 检查是否为同音字
    homophone_match = check_homophone(correct_name, resolved_guess, enable_homophone=self.enable_homophone)
    # 综合判断是否正确
    is_correct = (similarity > self.similarity_threshold) or (calculate > self.calculate_threshold) or homophone_match

    logger.debug(
        f"[答题判断] 正确答案: {correct_name}, 用户回答: {resolved_guess}, 相似度: {similarity:.2f}, "
        f"字匹配率: {calculate:.2f}, 同音匹配: {homophone_match}, 阈值: {self.similarity_threshold}/{self.calculate_threshold}, "
        f"结果: {is_correct}"
    )

    sender_name = event.get_sender_name()

    # 如果是比赛模式，更新比赛数据
    if is_group and match and group_id is not None:
        self.match_sessions[group_id] = event.unified_msg_origin
        await self.match_repo.add_participant(match.match_id, str(sender_id), sender_name)
        if is_correct:
            await self.match_repo.increment_participant_score(match.match_id, str(sender_id))
            # 取消当前题目的自动提示任务
            if group_id in self.match_next_task:
                self._safe_cancel_task(self.match_next_task.pop(group_id, None))
        else:
            await self.match_repo.increment_participant_wrong(match.match_id, str(sender_id))

    # 处理回答结果
    if is_correct:
        chain = [
            Comp.At(qq=sender_id),
            Comp.Plain(f" 回答正确! 答案为: {correct_name}"),
        ]
        responses.append(event.chain_result(chain))
        responses.append(await self.send_original_image(user_id, event))  # 发送原图

        # 更新用户正确计数
        await self.user_qna_repo.increment_correct_count(
            user_id=sender_id,
            user_name=sender_name,
        )

        # 比赛模式：自动出下一题 / 自动结束
        if is_group and match and group_id is not None:
            # 重新获取活跃比赛，避免已自动结束后再次结算导致重复荣誉
            match_now = await self.match_repo.get_active_match(group_id)
            if match_now and match_now.is_active:
                # 若已经有人推进到下一题，当前协程无需重复出题
                existing = self.player.get(group_id)
                if not (existing and existing.get("status") in {"active", "loading"}):
                    end_reason = await self._get_match_end_reason(match_now)
                    if end_reason:
                        ended_match_name, _, ended_top_participants = await self._end_match_and_collect_top(
                            group_id,
                            match_now,
                        )
                        if end_reason == "time_limit":
                            responses.append(
                                event.plain_result(f"⏱️ 已达到时间限制，比赛「{ended_match_name}」自动结束！")
                            )
                        else:
                            responses.append(
                                event.plain_result(f"📝 已达到题目上限，比赛「{ended_match_name}」自动结束！")
                            )
                        match_end_payload = (ended_match_name, ended_top_participants)
                    else:
                        next_bytes = await self.fc_init(group_id)
                        if next_bytes and next_bytes != "already_exists":
                            self.match_question_state[group_id] = time.time()
                            self._schedule_match_hint(group_id)
                            responses.append(
                                event.chain_result(
                                    [
                                        Comp.Plain("下一题来啦！\n干员立绘,请使用/fcc [干员名称] 进行猜测"),
                                        Comp.Image.fromBytes(next_bytes),
                                    ]
                                )
                            )
                        else:
                            responses.append(event.plain_result("下一题获取失败，请管理员使用 /ccl 比赛开始 重试"))
    else:
        chain = [
            Comp.At(qq=sender_id),
            Comp.Plain(" 回答错误!"),
        ]
        responses.append(event.chain_result(chain))
        # 更新用户错误计数
        await self.user_qna_repo.increment_wrong_count(
            user_id=sender_id,
            user_name=sender_name,
        )

    return responses, match_end_payload

async def iter_match_end_leaderboard(
    self,
    event: AstrMessageEvent,
    match_end_payload: tuple[str, list],
) -> AsyncIterator[Any]:
    """Post-lock output for `/fcc` when a match ends (image preferred, text fallback)."""
    ended_match_name, ended_top_participants = match_end_payload
    async for result in generate_image_or_fallback(
        event=event,
        generate_image_func=lambda: self.renderer.generate_match_leaderboard_image(
            ended_match_name,
            ended_top_participants,
            title=f"比赛「{ended_match_name}」已结束排行榜",
        ),
        generate_text_func=lambda: generate_match_leaderboard_text(
            ended_match_name,
            ended_top_participants,
            ended=True,
        ),
    ):
        yield result

async def handle_fce(
    self,
    event: AstrMessageEvent,
    *,
    user_id: str,
    sender_id: str,
    is_group: bool,
    group_id: str | None,
) -> list[Any]:
    """Core logic for `/fce` (expects room lock is held by caller)."""
    responses: list[Any] = []

    # 检查比赛模式下是否有权限
    match = await self.match_repo.get_active_match(group_id) if is_group else None
    if match and self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
        responses.append(event.plain_result("❌ 比赛期间只有管理员可以强制结束"))
    elif not has_active_game(self.player, user_id):
        responses.append(event.plain_result("没有初始化房间,请使用/fc"))
    else:
        answer = self.player[user_id]["name"]  # 获取答案
        chain = [
            Comp.At(qq=sender_id),
            Comp.Plain(f" 游戏已结束,答案为: {answer}"),
        ]
        responses.append(event.chain_result(chain))
        responses.append(await self.send_original_image(user_id, event))  # 发送原图

    return responses

async def handle_fct(
    self,
    event: AstrMessageEvent,
    *,
    user_id: str,
    sender_id: str,
    is_group: bool,
    group_id: str | None,
) -> Any | None:
    """Core logic for `/fct` (expects room lock is held by caller)."""
    response = None

    # 检查比赛模式下是否有权限（仅群聊）
    match = await self.match_repo.get_active_match(group_id) if is_group else None
    if match and self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
        response = event.plain_result("❌ 比赛期间只有管理员可以使用提示")
    elif not has_active_game(self.player, user_id):
        response = event.plain_result("没有初始化房间,请使用/fc")
    else:
        hint_text, _ = self._next_hint_text_and_advance(user_id)
        response = event.plain_result(hint_text)

        # 更新用户提示使用次数
        await self.user_qna_repo.increment_tip_count(
            user_id=event.get_sender_id(),
            user_name=event.get_sender_name(),
        )

    return response

async def handle_fcw(
    self,
    event: AstrMessageEvent,
    *,
    user_id: str,
    sender_id: str,
    is_group: bool,
    group_id: str | None,
) -> Any | None:
    """Core logic for `/fcw` (expects room lock is held by caller)."""
    response = None

    # 检查比赛模式下是否有权限（仅群聊）
    match = await self.match_repo.get_active_match(group_id) if is_group else None
    if match and self.admin_ids and sender_id not in [str(x) for x in self.admin_ids]:
        response = event.plain_result("❌ 比赛期间只有管理员可以使用提示")
    elif not has_active_game(self.player, user_id):
        response = event.plain_result("没有初始化房间,请使用/fc")
    else:
        char_data = self.data.get(self.player[user_id]["name"], {})

        logger.info(f"[fcw] player={self.player[user_id]}, char_data keys={list(char_data.keys()) if char_data else 'None'}")

        # 获取职业及分支
        profession = char_data.get("职业及分支", char_data.get("职业分支", "该干员没有该属性"))
        # 星级转换为中文
        star = char_data.get("星级", "")
        star_map = {"1": "一星", "2": "二星", "3": "三星", "4": "四星", "5": "五星", "6": "六星"}
        star_cn = star_map.get(str(star), star)
        # 阵营
        camp = char_data.get("阵营", char_data.get("所属阵营", "该干员没有该属性"))

        # 构建提示消息
        msg = "💡 一次性提示:\n"
        msg += f"职业: {profession}\n"
        msg += f"星级: {star_cn}\n"
        msg += f"阵营: {camp}"

        response = event.plain_result(msg)

        # 设置提示计数为4（跳过属性提示阶段）
        self.player[user_id]["fctn"] = 4
        # 更新用户提示使用次数
        await self.user_qna_repo.increment_tip_count(
            user_id=sender_id,
            user_name=event.get_sender_name(),
            increment=3,
        )

    return response
