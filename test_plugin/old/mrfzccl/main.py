from astrbot.api.event import MessageChain, filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.star import StarTools

from .src.QnAStatsRenderer import QnAStatsRenderer
from .src.tool import (
    generate_match_leaderboard_text,
    has_active_game,
    parse_aliases,
)
from .src.db.repo import UserQnARepo, MatchRepo
from .src.db.database import DBManager

from .src.handlers import ccl_admin, ccl_leaderboard, ccl_match, fc_handlers

from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timedelta
from urllib.parse import urlparse
from io import BytesIO
from pathlib import Path
from PIL import Image
import numpy as np
import traceback
import asyncio
import aiohttp
import ipaddress
import random
import json
import time
import os
import re

# 注册插件，指定插件名、作者、描述和版本号
@register("mrfzccl", "Lishining", "你知道的,我一直是明日方舟高手", "1.0.0")
class Mrfzccl(Star):
    _question_candidate_names: np.ndarray
    _question_candidate_urls: List[List[str]]
    _question_candidate_low_idx: np.ndarray
    _question_candidate_normal_idx: np.ndarray
    _question_cache_data_id: Optional[int]
    _question_cache_kw_sig: Optional[tuple]
    _question_rng: np.random.Generator
    recent_characters: List[str]

    # 插件初始化方法
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context, config)  # 调用父类初始化
        self.Config = config  # 保存配置对象
        self.player: Dict[str, Dict[str, Any]] = {}  # 存储玩家游戏状态
        self.original_images: Dict[str, Image.Image] = {}  # 保存原始图片对象
        self.is_load = False  # 数据加载标志
        self._shutting_down = False  # 添加关闭标志，用于优雅关闭

        # 是否对排行榜类进行管理员限制
        self.require_admin = self.Config.get("require_admin", True)

        # 提示信息类型映射字典
        self.fct_key = {
            0: "职业及分支",  # 第一个提示：职业
            1: "星级",  # 第二个提示：星级
            2: "阵营",  # 第三个提示：阵营
            3: "获取方式",  # 第四个提示：获取方式
        }

        # 从配置文件读取相似度阈值
        self.similarity_threshold = self.Config.get("similarity_threshold", 0.5)
        # 从配置文件读取字符匹配阈值
        self.calculate_threshold = self.Config.get("calculate_threshold", 0.5)
        # 是否启用同音字匹配
        self.enable_homophone = self.Config.get("enable_homophone", False)

        # 每日限制配置
        self.daily_limit = self.Config.get("daily_game_limit", 10)  # 每日游戏次数限制
        self.daily_usage: dict = {}  # 记录每日使用情况
        self.daily_counter: dict = {}  # 记录每日计数器

        # 比赛状态追踪
        self.match_question_state: dict[str, float] = {}  # group_id -> 当前题目开始时间戳
        self.match_next_task: dict[str, asyncio.Task] = {}  # group_id -> 当前题目的自动提示任务
        self.match_loop_task: dict[str, asyncio.Task] = {}  # group_id -> 比赛结束检测循环任务
        self.match_sessions: dict[str, str] = {}  # group_id -> unified_msg_origin（用于主动消息）
        self.match_locks: dict[str, asyncio.Lock] = {}  # room_id(group_id/私聊user_id) -> 锁，防止并发触发导致状态错乱
        self._room_lock_last_used: dict[str, float] = {}  # room_id -> 最近一次使用时间戳（用于清理长期闲置锁）

        # 防重复配置
        self.recent_characters: list = []  # 最近出现的干员列表
        self.max_recent_count = 20  # 最大记录数量

        # 别名系统
        self.alias_map: dict = {}  # 干员别名映射
        self._load_aliases()  # 加载别名配置

        # 低权重干员配置（出现概率较低的干员）
        self.low_weight_keywords = self.Config.get("low_weight_characters", "预备干员,机师,W,SideStory").split(",")
        self.low_weight_ratio = self.Config.get("low_weight_ratio", 0.2)  # 低权重干员出现概率

        # 比赛相关配置
        self.match_question_limit = self.Config.get("match_question_limit", 0)  # 比赛题目数量限制
        self.match_time_limit = self.Config.get("match_time_limit", 0)  # 比赛时间限制
        self.match_hint_delay = self.Config.get("match_hint_delay", 0)  # 比赛超时自动提示（秒，0关闭）
        self.admin_ids = self.Config.get("admin_ids", [])  # 管理员ID列表

        # 设置默认配置
        self.target_size = self.Config.get("target_size", 128)  # 图片目标尺寸
        self.easy_probability = self.Config.get("easy_probability", 0.6)  # 简单难度概率
        self.medium_probability = self.Config.get("medium_probability", 0.3)  # 中等难度概率
        self.hard_probability = self.Config.get("hard_probability", 0.1)  # 困难难度概率

        # 添加 HTTP 会话管理
        self._session: Optional[aiohttp.ClientSession] = None
        self._executor = None  # 线程池执行器

        # 获取存储目录配置
        self.storage_dir = str(StarTools.get_data_dir())
        logger.info(f"[Mrfzccl] 存储目录: {self.storage_dir}")

        # 确保存储目录存在
        os.makedirs(self.storage_dir, exist_ok=True)

        # 构建数据库路径
        self.db_path = os.path.join(self.storage_dir, "mrfzccl.db")
        logger.debug(f"[Mrfzccl] 数据库目录: {self.db_path}")

        # 初始化数据库管理器
        self.db = DBManager(
            db_path=self.db_path
        )
        # 初始化用户问答仓库
        self.user_qna_repo = UserQnARepo(self.db)

        # 初始化比赛仓库
        self.match_repo = MatchRepo(self.db)  # 比赛仓库

        # 构建临时图片路径
        self.img_tmp_path = Path(self.storage_dir) / "tmp"
        self.img_tmp_path.mkdir(parents=True, exist_ok=True)

        # 初始化问答统计渲染器
        renderer_theme = self.Config.get("renderer_theme", "light")
        self.renderer = QnAStatsRenderer(output_dir=str(self.img_tmp_path), theme=renderer_theme)
        logger.info(f"[Mrfzccl] 渲染主题: {renderer_theme}")

        # 构建数据文件路径
        data_path = self.Config.get("mrfz_data_path", "arknights_skins_dict.json")
        # 如果是相对路径，将其转换为绝对路径
        if not os.path.isabs(data_path):
            # 获取插件所在目录
            data_path = "arknights_skins_dict.json"
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            data_path = os.path.join(plugin_dir, data_path)
        if not data_path:
            logger.error("[Mrfzccl] 未配置数据文件路径")
            return
        try:
            logger.info(f"[Mrfzccl] 数据文件路径: {data_path}")
            if not os.path.exists(data_path):
                logger.error(f"[Mrfzccl] 数据文件不存在: {data_path}")
                return
            logger.info("[Mrfzccl] 数据文件存在，开始读取")
            # 读取并解析JSON数据文件
            with open(data_path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            logger.info("[Mrfzccl] JSON解析成功")
            if not isinstance(self.data, dict):
                logger.error("[Mrfzccl] 数据文件格式错误: 应为字典类型")
                return
            self.is_load = True  # 设置数据加载成功标志
            logger.info(f"[Mrfzccl] 数据加载成功，共加载 {len(self.data)} 个角色")
        except json.JSONDecodeError as e:
            logger.error(f"[Mrfzccl] JSON解析错误: {e}")
            logger.error(traceback.format_exc())
        except FileNotFoundError as e:
            logger.error(f"[Mrfzccl] 文件未找到: {e}")
            logger.error(traceback.format_exc())
        except PermissionError as e:
            logger.error(f"[Mrfzccl] 权限错误: {e}")
            logger.error(traceback.format_exc())
        except Exception as e:
            logger.error(f"[Mrfzccl] 加载数据文件时发生未知错误: {e}")
            logger.error(traceback.format_exc())

        # 清理任务相关
        self.cleanup_task: asyncio.Task | None = None
        self.cleanup_running = True

    # ========== 游戏相关指令 ==========
    # 初始化游戏命令
    @filter.command("fc")
    async def fc(self, event: AstrMessageEvent):
        """开始游戏 /fc"""
        # 检查数据是否加载成功
        if not self.is_load:
            yield event.chain_result([
                Comp.At(qq=event.get_sender_id()),  # @发送者
                Comp.Plain(" 插件未加载成功，请联系管理员配置数据文件")
            ])
            return

        # 获取用户ID和群组ID（比赛仅在群聊有效）
        group_id_raw = event.get_group_id()
        sender_id = str(event.get_sender_id())
        is_group = group_id_raw is not None
        group_id = str(group_id_raw) if is_group else None
        user_id = group_id if is_group else sender_id

        response = None
        room_lock = self._get_match_lock(user_id)
        async with room_lock:
            response = await fc_handlers.handle_fc(
                self,
                event,
                user_id=user_id,
                sender_id=sender_id,
                is_group=is_group,
                group_id=group_id,
            )

        if response is not None:
            yield response

    # 进行猜测命令
    @filter.command("fcc")
    async def fcc(self, event: AstrMessageEvent):
        """进行猜题 /fcc [干员名称]"""
        # 获取群组ID
        group_id_raw = event.get_group_id()
        sender_id = str(event.get_sender_id())
        is_group = group_id_raw is not None
        group_id = str(group_id_raw) if is_group else None
        user_id = group_id if is_group else sender_id

        room_lock = self._get_match_lock(user_id)
        async with room_lock:
            responses, match_end_payload = await fc_handlers.handle_fcc(
                self,
                event,
                user_id=user_id,
                sender_id=sender_id,
                is_group=is_group,
                group_id=group_id,
            )

        for r in responses:
            yield r

        if match_end_payload:
            async for result in fc_handlers.iter_match_end_leaderboard(self, event, match_end_payload):
                yield result

    # 强制结束游戏命令
    @filter.command("fce")
    async def fce(self, event: AstrMessageEvent):
        """强置结束游戏 /fce"""
        group_id_raw = event.get_group_id()
        sender_id = str(event.get_sender_id())
        is_group = group_id_raw is not None
        group_id = str(group_id_raw) if is_group else None
        user_id = group_id if is_group else sender_id

        room_lock = self._get_match_lock(user_id)
        async with room_lock:
            responses = await fc_handlers.handle_fce(
                self,
                event,
                user_id=user_id,
                sender_id=sender_id,
                is_group=is_group,
                group_id=group_id,
            )

        for r in responses:
            yield r

    # 获取提示命令
    @filter.command("fct")
    async def fct(self, event: AstrMessageEvent):
        """获取提示 /fct"""
        group_id = event.get_group_id()
        sender_id = str(event.get_sender_id())
        is_group = group_id is not None
        group_id_str = str(group_id) if is_group else None
        user_id = group_id_str if is_group else sender_id

        response = None
        room_lock = self._get_match_lock(user_id)
        async with room_lock:
            response = await fc_handlers.handle_fct(
                self,
                event,
                user_id=user_id,
                sender_id=sender_id,
                is_group=is_group,
                group_id=group_id_str,
            )

        if response is not None:
            yield response

    # 一次性获取三条提示命令
    @filter.command("fcw")
    async def fcw(self, event: AstrMessageEvent):
        """一次性获取三条提示 /fcw"""
        group_id = event.get_group_id()
        sender_id = str(event.get_sender_id())
        is_group = group_id is not None
        group_id_str = str(group_id) if is_group else None
        user_id = group_id_str if is_group else sender_id

        response = None
        room_lock = self._get_match_lock(user_id)
        async with room_lock:
            response = await fc_handlers.handle_fcw(
                self,
                event,
                user_id=user_id,
                sender_id=sender_id,
                is_group=is_group,
                group_id=group_id_str,
            )

        if response is not None:
            yield response

    # ========== ccl 相关指令 ==========
    # 创建命令组ccl
    @filter.command_group("ccl")
    def ccl(self):
        pass

    # ========== 排行榜相关函数 ==========
    # 获取正确个数的排行榜命令
    @ccl.command("排行榜")
    async def correct_answers_leaderboard(self, event: AstrMessageEvent):
        """获取正确个数的排行榜 /ccl 排行榜"""
        async for r in ccl_leaderboard.handle_correct_answers_leaderboard(self, event):
            yield r

    # 获取错误个数的排行榜命令
    @ccl.command("错误排行榜")
    async def wrong_answers_leaderboard(self, event: AstrMessageEvent):
        """获取错误个数的排行榜 /ccl 错误排行榜"""
        async for r in ccl_leaderboard.handle_wrong_answers_leaderboard(self, event):
            yield r

    # 获取使用提示次数的排行榜命令
    @ccl.command("提示排行榜")
    async def hints_usage_leaderboard(self, event: AstrMessageEvent):
        """获取使用提示次数的排行榜 /ccl 提示排行榜"""
        async for r in ccl_leaderboard.handle_hints_usage_leaderboard(self, event):
            yield r

    # 获取个人信息获取命令
    @ccl.command("名片")
    async def user_profile_retrieval(self, event: AstrMessageEvent, user_id: str | None = None):
        """获取个人信息获取 /ccl 名片 [user_id] (如果user_id为空默认为发送人)"""
        async for r in ccl_leaderboard.handle_user_profile_retrieval(self, event, user_id=user_id):
            yield r

    # ========== 比赛相关函数 ==========
    # 比赛帮助命令
    @ccl.command("比赛帮助")
    async def match_help(self, event: AstrMessageEvent):
        """比赛模式帮助"""
        async for r in ccl_match.handle_match_help(self, event):
            yield r

    # 创建比赛命令
    @ccl.command("比赛创建")
    async def match_create(self, event: AstrMessageEvent, name: str = "", question_limit: int = 0, time_limit: int = 0):
        """创建比赛（仅管理员）用法: /ccl 比赛创建 [名称] [题目限制] [时间限制(分钟)]
        例如: /ccl 比赛创建 春节赛 20 30 表示创建名称为"春节赛"、答完20题自动结束、最多30分钟的比赛
        题目限制填0表示不限制，时间限制填0表示不限制。比赛开始后，参与答题的用户自动成为参赛者"""
        async for r in ccl_match.handle_match_create(
            self,
            event,
            name=name,
            question_limit=question_limit,
            time_limit=time_limit,
        ):
            yield r

    # 比赛游戏循环
    @ccl.command("比赛开始")
    async def match_start(self, event: AstrMessageEvent):
        """使用`/ccl 比赛开始`开始比赛（仅管理员）"""
        ok, group_id, error_resp = await ccl_match.match_start_precheck(self, event)
        if not ok:
            if error_resp is not None:
                yield error_resp
            return

        room_lock = self._get_match_lock(group_id)
        async with room_lock:
            result = await ccl_match.match_start_inlock(self, group_id)

        yield ccl_match.build_match_start_response(event, result)

        # 创建比赛循环任务，用于检查结束条件
        self.match_loop_task[group_id] = asyncio.create_task(self._match_game_loop(group_id))

    # 结束比赛命令
    @ccl.command("比赛结束")
    async def match_end(self, event: AstrMessageEvent):
        """使用`/ccl 比赛结束`结束比赛（仅管理员）"""
        ok, group_id, error_resp = await ccl_match.match_end_precheck(self, event)
        if not ok:
            if error_resp is not None:
                yield error_resp
            return

        room_lock = self._get_match_lock(group_id)
        async with room_lock:
            ended, match_name, top_participants = await ccl_match.match_end_inlock(self, group_id)

        if not ended:
            yield event.plain_result("❌ 当前没有进行中的比赛")
            return

        async for r in ccl_match.iter_match_end_results(self, event, match_name, top_participants):
            yield r

    # 比赛排行榜命令
    @ccl.command("比赛排行")
    async def match_leaderboard(self, event: AstrMessageEvent):
        """使用`/ccl 比赛排行`获取比赛排行榜"""
        async for r in ccl_match.handle_match_leaderboard(self, event):
            yield r

    # 清除用户数据命令
    @ccl.command("清除数据")
    async def reset_user_data(self, event: AstrMessageEvent, target_user_id: str = ""):
        """清除用户答题数据（仅管理员）/ccl 清除数据 [user_id]"""
        async for r in ccl_admin.handle_reset_user_data(self, event, target_user_id=target_user_id):
            yield r

    # 清除用户荣誉命令
    @ccl.command("清除荣誉")
    async def reset_user_honors_cmd(self, event: AstrMessageEvent, target_user_id: str = ""):
        """清除用户荣誉数据（仅管理员）/ccl 清除荣誉 [user_id]"""
        async for r in ccl_admin.handle_reset_user_honors_cmd(self, event, target_user_id=target_user_id):
            yield r

    # 清除所有用户数据命令
    @ccl.command("清除所有数据")
    async def reset_all_data_cmd(self, event: AstrMessageEvent):
        """清除所有用户的答题数据（仅管理员）/ccl 清除所有数据"""
        async for r in ccl_admin.handle_reset_all_data_cmd(self, event):
            yield r

    # 清除所有用户荣誉命令
    @ccl.command("清除所有荣誉")
    async def reset_all_honors_cmd(self, event: AstrMessageEvent):
        """清除所有用户的荣誉数据（仅管理员）/ccl 清除所有荣誉"""
        async for r in ccl_admin.handle_reset_all_honors_cmd(self, event):
            yield r

    # 授予用户荣誉命令
    @ccl.command("授予荣誉")
    async def grant_honor_cmd(self, event: AstrMessageEvent, target_user_id: str = "", rank: int = 1, match_name: str = "", correct_count: int = 0):
        """授予用户特定荣誉（仅管理员）/ccl 授予荣誉 [user_id] [名次] [比赛名称] [答对数量]
        例如: /ccl 授予荣誉 123456 1 测试赛 10"""
        async for r in ccl_admin.handle_grant_honor_cmd(
            self,
            event,
            target_user_id=target_user_id,
            rank=rank,
            match_name=match_name,
            correct_count=correct_count,
        ):
            yield r

    # ========== 工具类相关函数 ==========
    # 发送原始图片
    async def send_original_image(self, user_id: str, event: AstrMessageEvent):
        if user_id in self.original_images:
            try:
                original_image = self.original_images[user_id]
                loop = asyncio.get_running_loop()
                # 调整图片大小
                resized_original = await loop.run_in_executor(
                    None,
                    self.resize_to_target,
                    original_image,
                    self.target_size
                )
                # 将图片转换为字节流
                img_bytes = self.pil_image_to_bytes(resized_original)
                output_data = event.chain_result([
                    Comp.Plain("正确答案的完整立绘:"),
                    Comp.Image.fromBytes(img_bytes)
                ])
                self.end_game(user_id)  # 结束游戏
                return output_data
            except Exception as e:
                logger.error(f"[send_original_image] 发送原始图片失败: {e}")
                self.end_game(user_id)
                return event.plain_result("发送正确答案图片失败")
        else:
            logger.warning(f"[send_original_image] 用户 {user_id} 没有原始图片")
            return event.plain_result("无法获取正确答案图片")

    # 结束游戏并清理资源
    def end_game(self, user_id: str) -> None:
        self.player.pop(user_id, None)
        self.original_images.pop(user_id, None)

    # 获取指定房间的比赛锁
    def _get_match_lock(self, room_id: str) -> asyncio.Lock:
        now = time.time()
        self._room_lock_last_used[room_id] = now

        lock = self.match_locks.get(room_id)
        if lock is None:
            lock = asyncio.Lock()
            self.match_locks[room_id] = lock

        return lock

    # 判断指定房间是否仍有运行中的比赛任务
    def _room_has_runtime(self, room_id: str) -> bool:
        """判断该 room_id 是否仍有运行态（游戏/比赛任务）"""
        data = self.player.get(room_id)
        if isinstance(data, dict) and data.get("status") in {"active", "loading"}:
            return True

        if room_id in self.match_question_state:
            return True
        if room_id in self.match_next_task:
            return True
        if room_id in self.match_loop_task:
            return True
        if room_id in self.match_sessions:
            return True

        return False

    # 清理长期闲置的房间锁，防止内存泄漏
    def _cleanup_stale_room_locks(self, max_idle_hours: int = 24) -> int:
        """清理长期闲置的 room lock，避免锁字典无限增长。"""
        try:
            cutoff = time.time() - float(max_idle_hours) * 3600
        except Exception:
            cutoff = time.time() - 24 * 3600

        removed = 0

        # 优先按“闲置时间”清理
        for rid, lock in list(self.match_locks.items()):
            last_used = float(self._room_lock_last_used.get(rid, 0) or 0)
            if last_used and last_used > cutoff:
                continue
            if lock.locked():
                continue
            if self._room_has_runtime(rid):
                continue
            self.match_locks.pop(rid, None)
            self._room_lock_last_used.pop(rid, None)
            removed += 1

        return removed

    # 安全取消异步任务
    @staticmethod
    def _safe_cancel_task(task: asyncio.Task | None) -> None:
        if not task:
            return
        try:
            if not task.done():
                task.cancel()
        except Exception:
            pass

    #  清理指定群组的比赛运行时状态
    def _clear_match_runtime(self, group_id: str) -> None:
        self.match_question_state.pop(group_id, None)

        hint_task = self.match_next_task.pop(group_id, None)
        self._safe_cancel_task(hint_task)

        loop_task = self.match_loop_task.pop(group_id, None)
        try:
            curr_task = asyncio.current_task()
        except Exception:
            curr_task = None
        if loop_task is not curr_task:
            self._safe_cancel_task(loop_task)

        self.match_sessions.pop(group_id, None)

        # 清理当前群的题目状态（防止比赛结束后仍可继续答题）
        self.end_game(group_id)

    # 获取比赛结束原因
    async def _get_match_end_reason(self, match) -> str | None:
        """返回比赛结束原因（time_limit/question_limit），不满足则返回 None。"""
        if not match:
            return None

        # 时间限制（分钟）
        try:
            time_limit_min = int(getattr(match, "time_limit", 0) or 0)
        except Exception:
            time_limit_min = 0

        if time_limit_min > 0:
            started_at = getattr(match, "started_at", None)
            if started_at:
                try:
                    if datetime.now() - started_at >= timedelta(minutes=time_limit_min):
                        return "time_limit"
                except Exception:
                    pass

        # 题目数量限制：按“正确题数（每题首次答对）”计
        try:
            q_limit = int(getattr(match, "question_limit", 0) or 0)
        except Exception:
            q_limit = 0

        if q_limit > 0:
            participants = await self.match_repo.get_participants(match.match_id)
            try:
                solved = sum(int(getattr(p, "correct_count", 0) or 0) for p in participants)
            except Exception:
                solved = 0
            if solved >= q_limit:
                return "question_limit"

        return None

    # 结束比赛并收集前十名参赛者
    async def _end_match_and_collect_top(self, group_id: str, match) -> tuple[str, int, list]:
        """结束比赛 + 清理运行态 + 返回 Top10 参赛者（已按得分排序），并保存荣誉。"""
        match_name = getattr(match, "match_name", "比赛")
        match_id = int(getattr(match, "match_id", 0) or 0)

        await self.match_repo.end_match(match_id)
        self._clear_match_runtime(group_id)

        participants = await self.match_repo.get_participants(match_id)
        participants.sort(key=lambda p: p.score, reverse=True)
        top_participants = participants[:10]

        for i, p in enumerate(top_participants, 1):
            await self.match_repo.save_honor(
                p.user_id, match_id, match_name, i,
                p.correct_count, p.wrong_count, p.score
            )

        return match_name, match_id, top_participants

    # 生成下一条提示文本并推进提示计数
    def _next_hint_text_and_advance(self, user_id: str) -> tuple[str, bool]:
        """生成下一条提示，并将 fctn +1（不含任何权限/活跃检查）。

        返回:
            (hint_text, has_more)
            has_more=False 表示本题已无更多有效提示（通常为名称已全部揭示）。
        """
        fctn = int(self.player.get(user_id, {}).get("fctn", 0) or 0)
        name = str(self.player.get(user_id, {}).get("name", "") or "")
        has_more = True

        if fctn <= 3:
            key = self.fct_key.get(fctn, "")
            char_data = self.data.get(name, {}) if name else {}

            if key == "职业及分支":
                value = char_data.get("职业及分支", char_data.get("职业分支", "该干员没有该属性"))
            elif fctn == 1:
                star_map = {"1": "一星", "2": "二星", "3": "三星", "4": "四星", "5": "五星", "6": "六星"}
                value = star_map.get(str(char_data.get("星级", "")), char_data.get("星级", ""))
            elif key == "阵营":
                value = char_data.get("阵营", char_data.get("所属阵营", "该干员没有该属性"))
            else:
                value = char_data.get(key, "该干员没有该属性")

            text = f"这个干员的{key}为:{value}"
        else:
            # 名称提示：每次出现增加 1/3（向上取整）
            if not name:
                text = "无法获取干员名称"
                has_more = False
            else:
                chunk = max(1, (len(name) + 2) // 3)  # ceil(len/3)
                step = max(1, fctn - 3)  # 1,2,3...
                reveal_len = min(len(name), chunk * step)
                text = f"这个干员的前{reveal_len}个字为:{name[:reveal_len]}"
                has_more = reveal_len < len(name)

        # 递增提示计数
        if user_id in self.player:
            self.player[user_id]["fctn"] = fctn + 1

        return text, has_more

    # 为当前题目安排超时自动提示
    def _schedule_match_hint(self, group_id: str) -> None:
        """为当前题目安排一次“超时自动提示”。delay<=0 时不启用。"""
        try:
            delay = int(self.match_hint_delay or 0)
        except Exception:
            delay = 0
        if delay <= 0:
            return

        session = self.match_sessions.get(group_id)
        if not session:
            return

        token = self.match_question_state.get(group_id)
        if not token:
            return

        # 取消旧任务
        if group_id in self.match_next_task:
            self._safe_cancel_task(self.match_next_task.pop(group_id, None))

        self.match_next_task[group_id] = asyncio.create_task(
            self._match_hint_after_delay(group_id, session, delay, float(token))
        )

    # 延迟后执行自动提示的循环任务
    async def _match_hint_after_delay(self, group_id: str, session: str, delay: int, token: float) -> None:
        try:
            interval = max(1, int(delay))
            while True:
                await asyncio.sleep(interval)

                if self._shutting_down:
                    return

                # 题目已变化/被清理：停止当前提示循环
                if self.match_question_state.get(group_id) != token:
                    return

                match = await self.match_repo.get_active_match(group_id)
                if not match or not match.is_active:
                    return

                if not has_active_game(self.player, group_id):
                    return

                lock = self._get_match_lock(group_id)
                async with lock:
                    # 二次确认：避免刚好答对/结束/切题后仍发送提示
                    if self.match_question_state.get(group_id) != token:
                        return
                    match2 = await self.match_repo.get_active_match(group_id)
                    if not match2 or not match2.is_active:
                        return
                    if not has_active_game(self.player, group_id):
                        return
                    hint_text, has_more = self._next_hint_text_and_advance(group_id)

                await self.context.send_message(session, MessageChain().message(f"💡 超时提示：{hint_text}"))
                if not has_more:
                    return

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning(f"[match] 自动提示任务异常 group_id={group_id}: {e}")

    # 加载别名映射
    def _load_aliases(self):
        alias_str = self.Config.get("character_aliases", "钛铱:白金,宫羽:澄闪,小刻:刻俄柏,小羊:艾雅法拉")
        self.alias_map = parse_aliases(alias_str)

    # 初始化游戏，返回临时文件路径
    async def fc_init(self, user_id: str) -> bytes | str | None:
        existing = self.player.get(user_id)
        if existing and existing.get("status") in {"active", "loading"}:
            return "already_exists"
        self.player[user_id] = {"status": "loading"}  # 设置加载状态
        try:
            # 提取题目
            question = await self.extract_questions()
            if not question:
                logger.error("[fc_init] 提取题目失败")
                self.player.pop(user_id, None)
                return None
            try:
                # 从URL获取图片
                image = await self.get_image_from_url(question["url"])
                if not image:
                    logger.error("[fc_init] 获取图片失败")
                    self.player.pop(user_id, None)
                    return None
            except Exception as e:
                logger.error(f"[fc_init] 获取图片失败,e:{e}")
                self.player.pop(user_id, None)
                return None

            # 保存原始图片
            self.original_images[user_id] = image.copy()
            question["status"] = "active"
            self.player[user_id] = question

            loop = asyncio.get_running_loop()

            # 根据概率选择难度（遮罩数量）
            r = random.random()
            cumulative = self.easy_probability
            if r < cumulative:
                block_count = 5  # 简单：5个遮罩
            elif r < cumulative + self.medium_probability:
                block_count = 3  # 中等：3个遮罩
            else:
                block_count = 1  # 困难：1个遮罩

            # 生成遮罩图片
            result, _ = await loop.run_in_executor(
                None,
                self.mask_image_with_random_blocks,
                image,
                block_count
            )
            # 调整图片大小
            resized = await loop.run_in_executor(
                None,
                self.resize_to_target,
                result,
                self.target_size
            )
            # 转换为字节流
            img_bytes = self.pil_image_to_bytes(resized)
            return img_bytes
        except Exception as e:
            logger.error(f"[fc_init] 初始化失败: {e}")
            logger.error(traceback.format_exc())
            if user_id in self.player:
                self.player.pop(user_id, None)
            return None

    # 获取明日方舟猜猜乐题目
    async def extract_questions(self) -> Optional[Dict[str, Any]]:
        try:
            if not self.data:
                logger.error("[extract_questions] 数据未加载")
                return None

            # ===== 构建候选缓存（一次性扫描，后续 O(1) 抽样）=====
            cache_data_id = getattr(self, "_question_cache_data_id", None)
            cache_kw_sig = getattr(self, "_question_cache_kw_sig", None)
            data_id = id(self.data)
            kw_sig = tuple(kw for kw in (self.low_weight_keywords or []) if isinstance(kw, str) and kw)

            if (
                cache_data_id != data_id
                or cache_kw_sig != kw_sig
                or not hasattr(self, "_question_candidate_names")
                or not hasattr(self, "_question_candidate_urls")
            ):
                def is_blocked_ip(hostname: Optional[str]) -> bool:
                    if not hostname:
                        return True
                    if str(hostname).strip().lower() == "localhost":
                        return True
                    try:
                        ip = ipaddress.ip_address(hostname)
                    except ValueError:
                        return False
                    return not ip.is_global

                candidate_names: list[str] = []
                candidate_urls: list[list[str]] = []
                is_low_weight: list[bool] = []

                low_keywords = [kw.strip() for kw in kw_sig if kw.strip()]

                for name, character_data in self.data.items():
                    if not isinstance(name, str) or not name:
                        continue
                    if not isinstance(character_data, dict):
                        continue
                    urls = character_data.get("original_url", None)
                    if not isinstance(urls, list) or not urls:
                        continue

                    valid_urls: list[str] = []
                    for u in urls:
                        if not isinstance(u, str):
                            continue
                        u = u.strip()
                        if not u or len(u) > 2048:
                            continue
                        parsed = urlparse(u)
                        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                            continue
                        if is_blocked_ip(parsed.hostname):
                            continue
                        valid_urls.append(u)

                    if not valid_urls:
                        continue

                    candidate_names.append(name)
                    candidate_urls.append(valid_urls)
                    is_low_weight.append(any(kw in name for kw in low_keywords))

                if not candidate_names:
                    logger.error("[extract_questions] 无可用题库（请检查 original_url 配置）")
                    return None

                self._question_candidate_names = np.array(candidate_names, dtype=object)
                self._question_candidate_urls = candidate_urls
                lw_mask = np.array(is_low_weight, dtype=bool)
                self._question_candidate_low_idx = np.flatnonzero(lw_mask)
                self._question_candidate_normal_idx = np.flatnonzero(~lw_mask)
                self._question_cache_data_id = data_id
                self._question_cache_kw_sig = kw_sig

            # ===== 随机抽题：使用 numpy RNG + 拒绝采样避免扫全表 =====
            rng = getattr(self, "_question_rng", None)
            if rng is None:
                rng = np.random.default_rng()
                self._question_rng = rng

            names_arr = self._question_candidate_names
            low_idx = getattr(self, "_question_candidate_low_idx", np.array([], dtype=int))
            normal_idx = getattr(self, "_question_candidate_normal_idx", np.array([], dtype=int))

            recent_set = set(self.recent_characters or [])
            # 如果候选数量小于 recent 记录，会导致无法抽到新题：直接清空
            if len(recent_set) >= len(names_arr):
                self.recent_characters = []
                recent_set = set()

            available_count = max(1, len(names_arr) - len(recent_set))
            try:
                low_prob = float(self.low_weight_ratio) / float(available_count)
            except Exception:
                low_prob = 0.0
            low_prob = max(0.0, min(1.0, low_prob))

            use_low = low_idx.size > 0 and normal_idx.size > 0 and rng.random() < low_prob
            primary_pool = low_idx if use_low else (normal_idx if normal_idx.size > 0 else low_idx)
            secondary_pool = normal_idx if primary_pool is low_idx else low_idx
            if primary_pool.size == 0:
                primary_pool = np.arange(len(names_arr), dtype=int)
                secondary_pool = np.array([], dtype=int)

            def pick_index(pool_arr: np.ndarray) -> Optional[int]:
                if pool_arr.size == 0:
                    return None
                for _ in range(60):
                    idx = int(pool_arr[int(rng.integers(pool_arr.size))])
                    if str(names_arr[idx]) not in recent_set:
                        return idx
                for idx in pool_arr:
                    i = int(idx)
                    if str(names_arr[i]) not in recent_set:
                        return i
                return None

            picked = pick_index(primary_pool)
            if picked is None:
                picked = pick_index(secondary_pool)
            if picked is None:
                self.recent_characters = []
                recent_set = set()
                picked = pick_index(primary_pool)
                if picked is None:
                    picked = pick_index(secondary_pool)
                if picked is None:
                    picked = int(rng.integers(len(names_arr)))

            random_name = str(names_arr[picked])
            url_list = self._question_candidate_urls[picked]
            random_url = url_list[int(rng.integers(len(url_list)))]

            # 更新最近干员列表
            self.recent_characters.append(random_name)
            if len(self.recent_characters) > self.max_recent_count:
                self.recent_characters.pop(0)

            return {"name": random_name, "url": random_url, "fctn": 0}
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"[extract_questions] 提取题目失败: {e}")
            return None
        except Exception as e:
            logger.error(f"[extract_questions] 提取题目时发生未知错误: {e}")
            logger.error(traceback.format_exc())
            return None

    # 路径处理
    def _get_absolute_path(self, path: str) -> str:
        if not path:
            raise ValueError("路径不能为空")
        return os.path.abspath(path)

    # 从URL异步获取图片
    async def get_image_from_url(self, url: str, timeout: int = 10) -> Optional[Image.Image]:
        try:
            # 检查URL协议
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"无效的URL协议: {url}")

            # 安全检查：防止访问内网地址
            parsed_url = urlparse(url)
            hostname = parsed_url.hostname
            if hostname:
                hostname_norm = str(hostname).strip().lower()
                if hostname_norm == "localhost":
                    raise ValueError(f"禁止访问内网地址: {hostname}")
                try:
                    ip = ipaddress.ip_address(hostname_norm)
                except ValueError:
                    ip = None
                if ip and not ip.is_global:
                    raise ValueError(f"禁止访问内网地址: {hostname}")

            # 获取HTTP会话
            session = await self._get_session()
            async with session.get(
                    url,
                    ssl=False  # 忽略SSL证书验证
            ) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}: {response.reason}")

                # 读取响应内容
                content = await response.read()
                if len(content) == 0:
                    raise Exception("下载的图片数据为空")
                if len(content) > 10 * 1024 * 1024:  # 限制10MB
                    raise Exception("图片文件过大")

                # 在线程池中加载图片
                loop = asyncio.get_running_loop()
                image = await loop.run_in_executor(
                    None,
                    self._load_image_from_bytes,
                    content
                )
                return image
        except (aiohttp.ClientError, ValueError) as e:
            logger.error(f"[get_image_from_url] 请求失败: {e}")
            raise
        except Exception as e:
            logger.error(f"[get_image_from_url] 处理图片时出错: {e}")
            raise

    # 同步加载图片（在线程池中执行）
    def _load_image_from_bytes(self, content: bytes) -> Image.Image:
        image = Image.open(BytesIO(content))
        # 检查图片格式
        if image.format not in ['JPEG', 'PNG', 'GIF', 'WEBP', 'BMP']:
            raise Exception(f"不支持的图片格式: {image.format}")
        image.load()

        # 检查图片尺寸
        width, height = image.size
        if width > 5000 or height > 5000:
            raise Exception(f"图片尺寸过大: {width}x{height}")
        return image

    # 提取并清理用户输入
    def extract_and_sanitize_input(self, text: str, keyword: str) -> str:
        if not text or not keyword:
            return ""
        # 使用正则表达式提取关键词后的内容
        pattern = rf'{re.escape(keyword)}\s*(.*)'
        match = re.search(pattern, text)
        if not match:
            return ""
        user_input = match.group(1).strip()
        # 清理特殊字符
        cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', '', user_input)
        # 限制长度
        if len(cleaned) > 50:
            cleaned = cleaned[:50]
        return cleaned

    # 遮挡图生成
    def mask_image_with_random_blocks(
            self,
            image: Image.Image,
            block_count: int = 5,
            mask_color: Tuple[int, int, int] = (0, 0, 0),
            min_width_percent: int = 10,
            max_width_percent: int = 20,
            min_height_percent: int = 10,
            max_height_percent: int = 20,
            min_gap_percent: int = 2,
            avoid_edges: bool = True
    ) -> Tuple[Image.Image, List[Tuple[int, int, int, int]]]:
        """
        高性能遮罩图片，只露出几个小方块，保持原始游戏逻辑

        参数:
            image: 原始图片
            block_count: 遮罩方块数量
            mask_color: 遮罩颜色(RGB)
            min/max_width/height_percent: 方块尺寸范围（图片尺寸的百分比）
            min_gap_percent: 方块间最小间距（图片尺寸的百分比）
            avoid_edges: 是否避免边缘

        返回:
            Tuple[遮罩后的图片, 方块坐标列表]
        """
        # 转换为RGBA模式（如果不是）
        if image.mode != 'RGBA':
            original_rgba = image.convert('RGBA')
        else:
            original_rgba = image.copy()

        width, height = original_rgba.size
        arr = np.array(original_rgba)

        # 创建遮罩层，填充 mask_color 并全覆盖
        mask_layer = np.zeros_like(arr)
        mask_layer[..., 0] = mask_color[0]
        mask_layer[..., 1] = mask_color[1]
        mask_layer[..., 2] = mask_color[2]
        mask_layer[..., 3] = 255  # 全不透明

        # 计算方块尺寸范围（像素）
        min_width = max(5, int(width * min_width_percent / 100))
        max_width = max(min_width, int(width * max_width_percent / 100))
        min_height = max(5, int(height * min_height_percent / 100))
        max_height = max(min_height, int(height * max_height_percent / 100))
        min_gap = int(min(width, height) * min_gap_percent / 100)
        edge_margin = min_gap if avoid_edges else 0

        blocks = []  # 存储方块坐标

        # 生成随机方块
        for _ in range(block_count):
            for attempt in range(100):  # 最多尝试100次
                # 随机方块尺寸
                w = random.randint(min_width, max_width)
                h = random.randint(min_height, max_height)
                max_x = width - w - edge_margin
                max_y = height - h - edge_margin
                if max_x <= edge_margin or max_y <= edge_margin:
                    break

                # 随机位置
                x1 = random.randint(edge_margin, max_x)
                y1 = random.randint(edge_margin, max_y)
                x2, y2 = x1 + w, y1 + h

                # 检查是否与已有方块冲突
                conflict = False
                for bx1, by1, bx2, by2 in blocks:
                    if not (x2 + min_gap < bx1 or x1 > bx2 + min_gap or
                            y2 + min_gap < by1 or y1 > by2 + min_gap):
                        conflict = True
                        break

                if not conflict:
                    blocks.append((x1, y1, x2, y2))
                    mask_layer[y1:y2, x1:x2, 3] = 0  # 方块区域透明
                    break

        # alpha 合成：遮罩层覆盖原图
        alpha = mask_layer[..., 3:4] / 255.0
        result_arr = arr * (1 - alpha) + mask_layer * alpha
        result_arr = result_arr.astype(np.uint8)
        result = Image.fromarray(result_arr, 'RGBA')
        return result, blocks

    # 按比例缩放图像，保持宽高比
    def resize_to_target(self, image: Image.Image, target_size: int) -> Image.Image:
        if target_size <= 0:
            target_size = 800
        w, h = image.size
        # 根据宽高比例计算新尺寸
        if w >= h:
            new_w = target_size
            new_h = int(target_size * h / w)
        else:
            new_h = target_size
            new_w = int(target_size * w / h)
        # 确保最小尺寸
        new_w = max(new_w, 100)
        new_h = max(new_h, 100)
        # 使用LANCZOS重采样算法（高质量）
        return image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # pil图片转变为bytes
    def pil_image_to_bytes(self, image: Image.Image, format: str = "PNG") -> bytes:
        buf = BytesIO()
        image.save(buf, format=format, optimize=True)  # optimize优化图片大小
        return buf.getvalue()

    # 主动消息发送比赛排行榜
    async def _send_match_leaderboard_to_session(
        self,
        session: str,
        match_name: str,
        top_participants: list,
        title: str,
    ) -> None:
        """主动消息发送比赛排行榜（优先图片，失败回退文本）。"""
        if self._shutting_down:
            return
        try:
            image_path = await self.renderer.generate_match_leaderboard_image(
                match_name,
                top_participants,
                title=title,
            )
            if image_path and os.path.exists(image_path):
                try:
                    await self.context.send_message(session, MessageChain().file_image(image_path))
                    return
                except Exception as e:
                    logger.warning(f"[match] 主动发送排行榜图片失败，回退文本: {e}")
        except Exception as e:
            logger.warning(f"[match] 比赛排行榜图片发送失败，回退文本: {e}")

        text = generate_match_leaderboard_text(match_name, top_participants, ended=True)
        try:
            await self.context.send_message(session, MessageChain().message(text))
        except Exception as e:
            logger.warning(f"[match] 主动发送排行榜文本失败: {e}")

    # 比赛游戏循环 - 用于检查结束条件
    async def _match_game_loop(self, group_id: str):
        await asyncio.sleep(2)

        while not self._shutting_down:
            await asyncio.sleep(5)

            match = await self.match_repo.get_active_match(group_id)
            if not match or not match.is_active:
                return

            end_reason = await self._get_match_end_reason(match)
            if not end_reason:
                continue

            lock = self._get_match_lock(group_id)
            session = None
            reason_text = ""
            match_name = ""
            top_participants = []
            async with lock:
                # 二次确认，避免与管理员/答题正确的自动结束并发导致重复结算
                match2 = await self.match_repo.get_active_match(group_id)
                if not match2 or not match2.is_active:
                    return

                session = self.match_sessions.get(group_id)
                if end_reason == "time_limit":
                    reason_text = f"⏱️ 已达到时间限制，比赛「{match2.match_name}」自动结束！"
                else:
                    reason_text = f"📝 已达到题目上限，比赛「{match2.match_name}」自动结束！"

                match_name, _, top_participants = await self._end_match_and_collect_top(group_id, match2)

                if not session:
                    logger.warning(f"[match] 缺少 session，无法主动发送比赛结束消息 group_id={group_id}")
                    return

            try:
                await self.context.send_message(session, MessageChain().message(reason_text))
                await self._send_match_leaderboard_to_session(
                    session=session,
                    match_name=match_name,
                    top_participants=top_participants,
                    title=f"比赛「{match_name}」已结束排行榜",
                )
            except Exception as e:
                logger.warning(f"[match] 主动发送比赛结束消息失败 group_id={group_id}: {e}")
            return

    # 插件初始化时
    async def initialize(self):
        await self.db.init_db()
        logger.debug(f"[Mrfzccl] 初始化数据库{self.db.db_url}")
        await self.start_cleanup_task()

    # 插件卸载时的清理钩子
    async def terminate(self):
        self._shutting_down = True
        # 取消比赛相关任务（防止卸载后仍在后台发送消息）
        for task in list(self.match_next_task.values()):
            self._safe_cancel_task(task)
        for task in list(self.match_loop_task.values()):
            self._safe_cancel_task(task)
        self.match_next_task.clear()
        self.match_loop_task.clear()
        self.match_sessions.clear()
        self.match_question_state.clear()

        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("[Mrfzccl] HTTP会话已关闭")
        await self.stop_cleanup_task()

    # 开启定时清理任务
    async def start_cleanup_task(self, interval_hours=1):
        """启动定时清理任务"""
        self.cleanup_running = True
        self.cleanup_task = asyncio.create_task(self._periodic_cleanup(interval_hours))
        return self.cleanup_task

    # 关闭定时清理任务
    async def stop_cleanup_task(self):
        """停止定时清理任务（带超时保护）"""
        self.cleanup_running = False

        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                # 最多等 2 秒让任务自己退出
                await asyncio.wait_for(self.cleanup_task, timeout=2)
            except asyncio.TimeoutError:
                logger.warning("[Mrfzccl] 清理任务取消超时，强制退出")
            except asyncio.CancelledError:
                # 正常情况
                pass
            finally:
                self.cleanup_task = None

    # 定时清理任务
    async def _periodic_cleanup(self, interval_hours=1):
        """可控制的定期清理"""
        while self.cleanup_running:
            try:
                # 等待指定时间
                await asyncio.sleep(interval_hours * 3600)

                # 检查是否还在运行
                if not self.cleanup_running:
                    break

                # 执行清理
                await self._cleanup_old_images()
                removed = self._cleanup_stale_room_locks(max_idle_hours=24)
                if removed:
                    logger.debug(f"[Mrfzccl] 清理闲置 room locks: {removed}")

            except asyncio.CancelledError:
                # 任务被取消
                break
            except Exception as e:
                # 记录错误但不停止任务
                logger.error(f"[Mrfzccl] 清理任务出错: {e}")
                await asyncio.sleep(60)  # 出错后等待1分钟再重试

    # 清理超过指定时间的图片
    async def _cleanup_old_images(self, max_age_hours=1):
        """清理超过指定时间的图片"""
        cutoff_time = time.time() - max_age_hours * 3600

        try:
            # 遍历临时目录中的所有PNG图片
            for file_path in self.img_tmp_path.glob("*.png"):
                if os.path.getmtime(file_path) < cutoff_time:
                    try:
                        os.remove(file_path)
                        logger.info(f"🧹 清理旧图片: {file_path}")
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"清理图片时出错: {e}")

    # 获取或创建 HTTP 会话
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)  # 限制连接池大小
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            logger.debug("[Mrfzccl] 创建新的HTTP会话")
        return self._session
