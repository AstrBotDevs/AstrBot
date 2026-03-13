from collections import Counter
import os
from typing import Any, Callable, Iterable, Mapping, Optional

from astrbot.api.event import AstrMessageEvent
import astrbot.api.message_components as Comp
from pypinyin import lazy_pinyin, Style
from datetime import datetime

def calculate_char_coverage_set(correct_name: str, guess_text: str) -> float:
    """
    计算guess_text包含correct_name中字符的比例（去重版本）

    Args:
        correct_name: 正确答案
        guess_text: 用户猜测的答案

    Returns:
        float: 字符覆盖率 (0-1之间)
    """
    if not correct_name:
        return 0.0

    # 转换为集合去重
    correct_chars = set(correct_name)
    guess_chars = set(guess_text)

    # 计算匹配的字符数比例
    matched_chars = correct_chars & guess_chars
    coverage = len(matched_chars) / len(correct_chars)

    return coverage

def calculate_char_coverage_counter(correct_name: str, guess_text: str) -> float:
    """
    计算guess_text包含correct_name中字符的比例（不去重版本）

    Args:
        correct_name: 正确答案
        guess_text: 用户猜测的答案

    Returns:
        float: 字符覆盖率 (0-1之间)
    """
    if not correct_name:
        return 0.0

    # 使用Counter统计字符出现次数
    correct_counter = Counter(correct_name)
    guess_counter = Counter(guess_text)

    # 计算总字符数和匹配的字符数
    total_chars = sum(correct_counter.values())
    matched_chars = 0

    for char, count in correct_counter.items():
        matched_chars += min(count, guess_counter.get(char, 0))

    coverage = matched_chars / total_chars if total_chars > 0 else 0.0

    return coverage

def generate_correct_leaderboard_text(users: Iterable[Any], summary: Optional[Mapping[str, Any]] = None) -> str:
    """生成正确量排行榜文本"""
    users = list(users or [])
    if not users:
        return "📊 当前还没有用户的答题记录哦~"

    message = "🏆 **正确量排行榜** 🏆\n\n"

    for i, user in enumerate(users, 1):
        if i == 1:
            medal = "🥇"
        elif i == 2:
            medal = "🥈"
        elif i == 3:
            medal = "🥉"
        else:
            medal = f"{i}."

        total_answers = getattr(user, "correct_count", 0) + getattr(user, "wrong_count", 0)
        accuracy = (getattr(user, "correct_count", 0) / total_answers * 100) if total_answers > 0 else 0

        message += f"{medal} {getattr(user, 'user_name', '-')}\n"
        message += (
            f"   ✅ 正确: {getattr(user, 'correct_count', 0)} | ❌ 错误: {getattr(user, 'wrong_count', 0)} | 💡 提示: {getattr(user, 'tip_count', 0)}\n"
        )
        updated_at = getattr(user, "updated_at", None)
        updated_str = updated_at.strftime("%Y-%m-%d") if hasattr(updated_at, "strftime") else "-"
        message += f"   📈 准确率: {accuracy:.1f}% | 📅 最后更新: {updated_str}\n\n"

    if summary:
        message += "📊 **统计信息**\n"
        message += f"总用户数: {summary.get('total_users', '-')} | 总答题数: {summary.get('total_questions', '-')}\n"
        message += f"总正确数: {summary.get('total_correct', '-')} | 总错误数: {summary.get('total_wrong', '-')}\n"
        message += f"平均正确数: {summary.get('avg_correct', 0):.1f}"

    return message

def generate_wrong_leaderboard_text(users: Iterable[Any]) -> str:
    """生成错误个数排行榜文本"""
    users = list(users or [])
    if not users:
        return "📊 当前还没有用户的答题记录哦~"

    message = "💥 **错误个数排行榜** 💥\n\n"

    for i, user in enumerate(users, 1):
        if i == 1:
            medal = "💣"
        elif i == 2:
            medal = "🧨"
        elif i == 3:
            medal = "🎆"
        else:
            medal = f"{i}."

        total_answers = getattr(user, "correct_count", 0) + getattr(user, "wrong_count", 0)
        error_rate = (getattr(user, "wrong_count", 0) / total_answers * 100) if total_answers > 0 else 0

        message += f"{medal} {getattr(user, 'user_name', '-')}\n"
        message += (
            f"   ❌ 错误: {getattr(user, 'wrong_count', 0)} | ✅ 正确: {getattr(user, 'correct_count', 0)} | 💡 提示: {getattr(user, 'tip_count', 0)}\n"
        )
        updated_at = getattr(user, "updated_at", None)
        updated_str = updated_at.strftime("%Y-%m-%d") if hasattr(updated_at, "strftime") else "-"
        message += f"   📉 错误率: {error_rate:.1f}% | 📅 最后更新: {updated_str}\n\n"

    return message

def generate_hints_leaderboard_text(users: Iterable[Any]) -> str:
    """生成提示次数排行榜文本"""
    users = list(users or [])
    if not users:
        return "📊 当前还没有用户的答题记录哦~"

    message = "💡 **提示次数排行榜** 💡\n\n"

    for i, user in enumerate(users, 1):
        if i == 1:
            medal = "🎯"
        elif i == 2:
            medal = "🔍"
        elif i == 3:
            medal = "🧩"
        else:
            medal = f"{i}."

        total_answers = getattr(user, "correct_count", 0) + getattr(user, "wrong_count", 0)
        tips_per_question = (getattr(user, "tip_count", 0) / total_answers) if total_answers > 0 else 0

        message += f"{medal} {getattr(user, 'user_name', '-')}\n"
        message += (
            f"   💡 提示: {getattr(user, 'tip_count', 0)} | ✅ 正确: {getattr(user, 'correct_count', 0)} | ❌ 错误: {getattr(user, 'wrong_count', 0)}\n"
        )
        updated_at = getattr(user, "updated_at", None)
        updated_str = updated_at.strftime("%Y-%m-%d") if hasattr(updated_at, "strftime") else "-"
        message += f"   📊 提示频率: {tips_per_question:.2f}/题 | 📅 最后更新: {updated_str}\n\n"

    return message

def generate_match_leaderboard_text(match_name: str, participants: Iterable[Any], ended: bool = False) -> str:
    """生成比赛排行榜文本（图片生成失败时的回退）"""
    participants = list(participants or [])
    if not participants:
        status = "已结束" if ended else "排行榜"
        return f"比赛「{match_name}」{status}\n\n暂无参赛记录"

    try:
        participants.sort(key=lambda p: float(getattr(p, "score", 0.0) or 0.0), reverse=True)
    except Exception:
        pass

    title = f"比赛「{match_name}」已结束\n排行榜" if ended else f"比赛「{match_name}」排行榜"
    message = f"{title}\n----------------\n"
    for i, p in enumerate(participants[:10], 1):
        user_name = getattr(p, "user_name", "-")
        correct = getattr(p, "correct_count", 0)
        wrong = getattr(p, "wrong_count", 0)
        try:
            score_str = f"{float(getattr(p, 'score', 0.0) or 0.0):.2f}"
        except Exception:
            score_str = "-"
        message += f"{i}. {user_name}: {correct}对 {wrong}错 {score_str}分\n"
    return message

def generate_user_profile_text(user_stats: Any, rank_info: Mapping[str, Any], honors=None, user_id: str | None = None) -> str:
    """生成用户个人信息文本"""
    honors = list(honors or [])

    title = getattr(user_stats, "user_name", None) if user_stats else None
    title = title or (user_id or "未知用户")
    message = f"👤 **用户信息 - {title}**\n\n"

    if not user_stats:
        message += "📊 **基础统计**\n"
        message += "暂无答题记录\n"
    else:
        total_answers = getattr(user_stats, "correct_count", 0) + getattr(user_stats, "wrong_count", 0)
        accuracy = (getattr(user_stats, "correct_count", 0) / total_answers * 100) if total_answers > 0 else 0

        message += "📊 **基础统计**\n"
        message += f"✅ 正确: {getattr(user_stats, 'correct_count', 0)}\n"
        message += f"❌ 错误: {getattr(user_stats, 'wrong_count', 0)}\n"
        message += f"💡 提示: {getattr(user_stats, 'tip_count', 0)}\n"
        message += f"🎯 准确率: {accuracy:.1f}%\n"
        message += f"📝 总答题数: {total_answers}\n\n"

        if rank_info:
            message += f"🏆 **排名信息** (共{rank_info.get('total_users', '?')}人)\n"
            message += f"✅ 正确排名: 第{rank_info.get('correct_rank', '?')}名\n"
            message += f"❌ 错误排名: 第{rank_info.get('wrong_rank', '?')}名\n"
            message += f"💡 提示排名: 第{rank_info.get('tip_rank', '?')}名\n\n"

        created_at = getattr(user_stats, "created_at", None)
        updated_at = getattr(user_stats, "updated_at", None)
        created_str = created_at.strftime("%Y-%m-%d %H:%M") if hasattr(created_at, "strftime") else "-"
        updated_str = updated_at.strftime("%Y-%m-%d %H:%M") if hasattr(updated_at, "strftime") else "-"

        message += "📅 **时间信息**\n"
        message += f"⏰ 注册时间: {created_str}\n"
        message += f"🔄 最后更新: {updated_str}\n"

    if honors:
        message += "\n🏅 **比赛荣誉**\n"
        for h in honors[:5]:
            try:
                score_str = f"{float(getattr(h, 'score', 0.0)):.1f}"
            except Exception:
                score_str = "-"
            message += (
                f"{getattr(h, 'medal', '')} {getattr(h, 'match_name', '-')}: "
                f"第{getattr(h, 'rank', '?')}名（✅{getattr(h, 'correct_count', 0)}/"
                f"❌{getattr(h, 'wrong_count', 0)}，S{score_str}）\n"
            )
    else:
        message += "\n暂无荣誉记录\n"

    return message

async def generate_image_or_fallback(
    event: AstrMessageEvent,
    generate_image_func: Callable[..., Any],
    generate_text_func: Callable[..., str],
    *args,
    **kwargs,
):
    """统一的图片生成和回退处理"""
    try:
        image_path = await generate_image_func(*args, **kwargs)

        if image_path and os.path.exists(image_path):
            yield event.chain_result([Comp.Image.fromFileSystem(image_path)])
            return

        text_message = generate_text_func(*args, **kwargs)
        yield event.plain_result(f"图片生成失败，使用文本模式显示\n\n{text_message}")

    except Exception as render_error:
        text_message = generate_text_func(*args, **kwargs)
        yield event.plain_result(f"图片生成失败，使用文本模式显示\n错误: {str(render_error)}\n\n{text_message}")

def parse_aliases(alias_str: str) -> dict[str, str]:
    """解析别名配置字符串为映射表：别名:正名,别名:正名"""
    alias_map: dict[str, str] = {}
    if not alias_str:
        return alias_map
    for pair in str(alias_str).split(","):
        if ":" not in pair:
            continue
        alias, name = pair.split(":", 1)
        alias = alias.strip()
        name = name.strip()
        if not alias or not name:
            continue
        alias_map[alias] = name
    return alias_map

def resolve_alias(name: str, alias_map: Mapping[str, str]) -> str:
    """将别名解析为正名（若不存在则返回原值）"""
    return (alias_map or {}).get(name, name)

def get_pinyin(text: str) -> str:
    """获取汉字的拼音（不带声调）"""
    return "".join(lazy_pinyin(text, style=Style.NORMAL))

def check_homophone(correct: str, guess: str, enable_homophone: bool = False) -> bool:
    """检查两个字符串是否同音（基于拼音）"""
    if not enable_homophone:
        return False
    return get_pinyin(correct) == get_pinyin(guess)

def check_daily_limit(user_id: str, daily_counter: dict, daily_limit: int) -> bool:
    """检查并更新每日计数器，返回是否允许继续游戏"""
    today = datetime.now().date()
    key = f"{user_id}_{today}"
    count = daily_counter.get(key, 0)
    if count >= daily_limit:
        return False
    daily_counter[key] = count + 1
    return True

def has_active_game(player: Mapping[str, Any], user_id: str) -> bool:
    """检查用户是否有活跃游戏"""
    data = (player or {}).get(user_id)
    return bool(data and data.get("status") == "active")
