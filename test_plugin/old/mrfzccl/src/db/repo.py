from datetime import datetime
from typing import List, Optional, Tuple
from sqlalchemy import desc, func, select, update, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import CursorResult

from .tables import UserQnAStats, Match, MatchParticipant, MatchHonor
from .database import DBManager

class UserQnARepo:
    """用户问答统计仓库，封装所有的数据库交互逻辑"""

    def __init__(self, db_manager: DBManager):
        self.db = db_manager

    # 获取或者创建用户数据
    async def get_or_create_user_stats(self, session: AsyncSession, user_id: str, user_name: str = "") -> UserQnAStats:
        """并发安全的 get_or_create 用户统计记录"""
        stmt = select(UserQnAStats).where(
            UserQnAStats.user_id == user_id
        )

        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        if record:
            # 如果用户名称有变化，更新用户名称
            if user_name and record.user_name != user_name:
                record.user_name = user_name
                record.updated_at = datetime.now()
            return record

        # 创建新记录（包含 tip_count）
        record = UserQnAStats(
            user_id=user_id,
            user_name=user_name or f"用户_{user_id}",
            correct_count=0,
            wrong_count=0,
            tip_count=0,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        session.add(record)

        try:
            await session.flush()
            return record
        except IntegrityError:
            # 并发下被其他事务插入，重新读取
            result = await session.execute(stmt)
            return result.scalar_one()

    # 获取用户数据
    async def get_user_stats_only(self, session: AsyncSession, user_id: str) -> Optional[UserQnAStats]:
        """
        只获取用户数据，如果用户不存在则返回None

        参数:
            session: 数据库会话
            user_id: 用户ID

        返回:
            UserQnAStats 或 None
        """
        stmt = select(UserQnAStats).where(
            UserQnAStats.user_id == user_id
        )

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    # ========== 增加操作 ==========

    # 增加答题正确数量
    async def increment_correct_count(self, user_id: str, user_name: str = "", increment: int = 1) -> bool:
        """增加用户答对次数（原子操作）"""
        async with self.db.get_session() as session:
            # 先尝试更新现有记录
            stmt = (
                update(UserQnAStats)
                .where(UserQnAStats.user_id == user_id)
                .values(
                    correct_count=UserQnAStats.correct_count + increment,
                    updated_at=datetime.now()
                )
            )

            result: CursorResult = await session.execute(stmt)

            if result.rowcount == 0:
                # 记录不存在，创建新记录
                record = await self.get_or_create_user_stats(session, user_id, user_name)
                record.correct_count += increment
                record.updated_at = datetime.now()
                await session.commit()
                return True

            # 如果提供了user_name，检查是否需要更新
            if user_name:
                user_stmt = select(UserQnAStats).where(UserQnAStats.user_id == user_id)
                user_result = await session.execute(user_stmt)
                user_record = user_result.scalar_one()
                if user_record.user_name != user_name:
                    user_record.user_name = user_name
                    user_record.updated_at = datetime.now()

            return True

    # 增加答题错误数量
    async def increment_wrong_count(self, user_id: str, user_name: str = "", increment: int = 1) -> bool:
        """增加用户答错次数（原子操作）"""
        async with self.db.get_session() as session:
            stmt = (
                update(UserQnAStats)
                .where(UserQnAStats.user_id == user_id)
                .values(
                    wrong_count=UserQnAStats.wrong_count + increment,
                    updated_at=datetime.now()
                )
            )

            result: CursorResult = await session.execute(stmt)

            if result.rowcount == 0:
                # 记录不存在，创建新记录
                record = await self.get_or_create_user_stats(session, user_id, user_name)
                record.wrong_count += increment
                record.updated_at = datetime.now()
                await session.commit()
                return True

            # 如果提供了user_name，检查是否需要更新
            if user_name:
                user_stmt = select(UserQnAStats).where(UserQnAStats.user_id == user_id)
                user_result = await session.execute(user_stmt)
                user_record = user_result.scalar_one()
                if user_record.user_name != user_name:
                    user_record.user_name = user_name
                    user_record.updated_at = datetime.now()

            return True

    # 增加提示次数
    async def increment_tip_count(self, user_id: str, user_name: str = "", increment: int = 1) -> bool:
        """增加用户提示次数（原子操作）"""
        async with self.db.get_session() as session:
            stmt = (
                update(UserQnAStats)
                .where(UserQnAStats.user_id == user_id)
                .values(
                    tip_count=UserQnAStats.tip_count + increment,
                    updated_at=datetime.now()
                )
            )

            result: CursorResult = await session.execute(stmt)

            if result.rowcount == 0:
                # 记录不存在，创建新记录
                record = await self.get_or_create_user_stats(session, user_id, user_name)
                record.tip_count += increment
                record.updated_at = datetime.now()
                await session.commit()
                return True

            # 如果提供了user_name，检查是否需要更新
            if user_name:
                user_stmt = select(UserQnAStats).where(UserQnAStats.user_id == user_id)
                user_result = await session.execute(user_stmt)
                user_record = user_result.scalar_one()
                if user_record.user_name != user_name:
                    user_record.user_name = user_name
                    user_record.updated_at = datetime.now()

            return True

    # 增加答题正确和答题错误数量
    async def increment_both_counts(self, user_id: str, user_name: str = "", correct_increment: int = 1, wrong_increment: int = 1) -> bool:
        """同时增加用户答对和答错次数（原子操作）"""
        async with self.db.get_session() as session:
            # 先尝试更新现有记录
            stmt = (
                update(UserQnAStats)
                .where(UserQnAStats.user_id == user_id)
                .values(
                    correct_count=UserQnAStats.correct_count + correct_increment,
                    wrong_count=UserQnAStats.wrong_count + wrong_increment,
                    updated_at=datetime.now()
                )
            )

            result: CursorResult = await session.execute(stmt)

            if result.rowcount == 0:
                # 记录不存在，创建新记录
                record = await self.get_or_create_user_stats(session, user_id, user_name)
                record.correct_count += correct_increment
                record.wrong_count += wrong_increment
                record.updated_at = datetime.now()
                await session.commit()
                return True

            # 如果提供了user_name，检查是否需要更新
            if user_name:
                user_stmt = select(UserQnAStats).where(UserQnAStats.user_id == user_id)
                user_result = await session.execute(user_stmt)
                user_record = user_result.scalar_one()
                if user_record.user_name != user_name:
                    user_record.user_name = user_name
                    user_record.updated_at = datetime.now()

            return True

    # 增加所有计数器（正确、错误、提示）
    async def increment_all_counts(self, user_id: str, user_name: str = "", correct_increment: int = 0, wrong_increment: int = 0, tip_increment: int = 0) -> bool:
        """同时增加用户所有计数器（原子操作）"""
        async with self.db.get_session() as session:
            # 构建更新值字典
            update_values = {"updated_at": datetime.now()}

            if correct_increment != 0:
                update_values["correct_count"] = UserQnAStats.correct_count + correct_increment
            if wrong_increment != 0:
                update_values["wrong_count"] = UserQnAStats.wrong_count + wrong_increment
            if tip_increment != 0:
                update_values["tip_count"] = UserQnAStats.tip_count + tip_increment

            # 如果没有实际更新，直接返回
            if len(update_values) == 1:  # 只有 updated_at
                return True

            # 先尝试更新现有记录
            stmt = (
                update(UserQnAStats)
                .where(UserQnAStats.user_id == user_id)
                .values(**update_values)
            )

            result: CursorResult = await session.execute(stmt)

            if result.rowcount == 0:
                # 记录不存在，创建新记录
                record = await self.get_or_create_user_stats(session, user_id, user_name)

                if correct_increment != 0:
                    record.correct_count += correct_increment
                if wrong_increment != 0:
                    record.wrong_count += wrong_increment
                if tip_increment != 0:
                    record.tip_count += tip_increment

                record.updated_at = datetime.now()
                await session.commit()
                return True

            # 如果提供了user_name，检查是否需要更新
            if user_name:
                user_stmt = select(UserQnAStats).where(UserQnAStats.user_id == user_id)
                user_result = await session.execute(user_stmt)
                user_record = user_result.scalar_one()
                if user_record.user_name != user_name:
                    user_record.user_name = user_name
                    user_record.updated_at = datetime.now()

            return True

    # ========== 查询操作 ==========

    # 按ID查找用户并获取当前排名
    async def get_user_stats_with_rank(self, user_id: str) -> Tuple[Optional[UserQnAStats], Optional[int], int]:
        """
        按ID查找用户并获取当前排名

        返回:
            (用户统计记录, 排名(从1开始), 总用户数)
            如果用户不存在，返回(None, None, 总用户数)
        """
        async with self.db.get_session() as session:
            # 获取总用户数
            total_stmt = select(func.count()).select_from(UserQnAStats)
            total_result = await session.execute(total_stmt)
            total_users = total_result.scalar_one() or 0

            if total_users == 0:
                return None, None, 0

            # 获取用户记录（包含 tip_count）
            user_stmt = select(UserQnAStats).where(UserQnAStats.user_id == user_id)
            user_result = await session.execute(user_stmt)
            user_record = user_result.scalar_one_or_none()

            if not user_record:
                return None, None, total_users

            # 计算排名: correct_count 越高排名越高
            # 使用窗口函数或子查询计算排名
            rank_stmt = select(
                func.count().label('rank')
            ).where(
                and_(
                    UserQnAStats.correct_count > user_record.correct_count,
                    UserQnAStats.user_id != user_id
                )
            )
            rank_result = await session.execute(rank_stmt)
            # 排名从1开始
            rank = (rank_result.scalar_one() or 0) + 1

            return user_record, rank, total_users

    # 获取用户统计数据（简单版本）
    async def get_user_stats(self, user_id: str) -> Optional[UserQnAStats]:
        """获取用户统计数据（包含 tip_count）"""
        async with self.db.get_session() as session:
            stmt = select(UserQnAStats).where(UserQnAStats.user_id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # 按照正确的题目数量从大到小排序，返回前N个用户
    async def get_top_users(self, limit: int = 10) -> List[UserQnAStats]:
        """
        按照正确的题目数量从大到小排序，返回前N个用户

        参数:
            limit: 返回的用户数量

        返回:
            排名前N的用户列表（包含 tip_count）
        """
        async with self.db.get_session() as session:
            stmt = (
                select(UserQnAStats)
                .order_by(desc(UserQnAStats.correct_count), UserQnAStats.updated_at)
                .limit(limit)
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())

    # 按照提示次数从多到少排序，返回前N个用户
    async def get_top_tip_users(self, limit: int = 10) -> List[UserQnAStats]:
        """
        按照提示次数从多到少排序，返回前N个用户

        参数:
            limit: 返回的用户数量

        返回:
            提示次数最多的用户列表
        """
        async with self.db.get_session() as session:
            stmt = (
                select(UserQnAStats)
                .order_by(desc(UserQnAStats.tip_count), desc(UserQnAStats.correct_count))
                .limit(limit)
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())

    # 获取用户提示次数统计
    async def get_user_tip_stats(self, user_id: str) -> Tuple[int, int, int]:
        """
        获取用户提示次数及相关统计

        返回:
            (tip_count, correct_count, wrong_count)
        """
        async with self.db.get_session() as session:
            stmt = select(
                UserQnAStats.tip_count,
                UserQnAStats.correct_count,
                UserQnAStats.wrong_count
            ).where(UserQnAStats.user_id == user_id)

            result = await session.execute(stmt)
            row = result.one_or_none()

            if row:
                return row.tip_count, row.correct_count, row.wrong_count
            return 0, 0, 0

    # ========== 创建/更新操作 ==========

    # 创建或更新用户统计记录（完整记录）
    async def create_or_update_user(self, user_id: str, user_name: str, correct_count: int = 0, wrong_count: int = 0, tip_count: int = 0) -> UserQnAStats:
        """创建或更新用户统计记录（完整记录，包含 tip_count）"""
        async with self.db.get_session() as session:
            record = await self.get_or_create_user_stats(session, user_id, user_name)

            # 更新数据
            record.correct_count = correct_count
            record.wrong_count = wrong_count
            record.tip_count = tip_count
            record.updated_at = datetime.now()

            return record

    # 批量创建或更新用户统计记录
    async def batch_create_or_update_users(self, users_data: List[dict]) -> int:
        """
        批量创建或更新用户统计记录

        参数:
            users_data: 用户数据列表，每个元素为字典，包含:
                - user_id: 用户ID
                - user_name: 用户名
                - correct_count: 答对数量
                - wrong_count: 答错数量
                - tip_count: 提示数量（可选）

        返回:
            成功处理的数量
        """
        if not users_data:
            return 0

        processed_count = 0
        async with self.db.get_session() as session:
            for user_data in users_data:
                try:
                    record = await self.get_or_create_user_stats(
                        session,
                        user_data['user_id'],
                        user_data.get('user_name', '')
                    )

                    # 更新数据（可以设置为增量或覆盖，这里用增量）
                    if 'correct_count' in user_data:
                        record.correct_count += user_data['correct_count']
                    if 'wrong_count' in user_data:
                        record.wrong_count += user_data['wrong_count']
                    if 'tip_count' in user_data:
                        record.tip_count += user_data['tip_count']

                    record.updated_at = datetime.now()
                    processed_count += 1

                except Exception as e:
                    # 记录错误但继续处理其他用户
                    print(f"处理用户 {user_data.get('user_id')} 时出错: {e}")
                    continue

            await session.commit()

        return processed_count

    # 更新用户提示次数（直接设置）
    async def update_tip_count(self, user_id: str, tip_count: int, user_name: str = "") -> bool:
        """更新用户提示次数（直接设置值）"""
        async with self.db.get_session() as session:
            stmt = (
                update(UserQnAStats)
                .where(UserQnAStats.user_id == user_id)
                .values(
                    tip_count=tip_count,
                    updated_at=datetime.now()
                )
            )

            result: CursorResult = await session.execute(stmt)

            if result.rowcount == 0:
                # 记录不存在，创建新记录
                record = await self.get_or_create_user_stats(session, user_id, user_name)
                record.tip_count = tip_count
                record.updated_at = datetime.now()
                await session.commit()
                return True

            # 如果提供了user_name，检查是否需要更新
            if user_name:
                user_stmt = select(UserQnAStats).where(UserQnAStats.user_id == user_id)
                user_result = await session.execute(user_stmt)
                user_record = user_result.scalar_one()
                if user_record.user_name != user_name:
                    user_record.user_name = user_name
                    user_record.updated_at = datetime.now()

            return True

    # ========== 其他操作 ==========

    # 分页获取用户排名
    async def get_user_rankings_page(self, page: int = 1, page_size: int = 20) -> Tuple[List[UserQnAStats], int]:
        """
        分页获取用户排名

        参数:
            page: 页码（从1开始）
            page_size: 每页数量

        返回:
            (当前页的用户列表, 总用户数)
        """
        async with self.db.get_session() as session:
            # 获取总用户数
            total_stmt = select(func.count()).select_from(UserQnAStats)
            total_result = await session.execute(total_stmt)
            total_users = total_result.scalar_one() or 0

            # 计算偏移量
            offset = (page - 1) * page_size

            # 获取分页数据
            stmt = (
                select(UserQnAStats)
                .order_by(desc(UserQnAStats.correct_count), UserQnAStats.updated_at)
                .offset(offset)
                .limit(page_size)
            )

            result = await session.execute(stmt)
            users = list(result.scalars().all())

            return users, total_users

    # 根据用户名关键词搜索用户
    async def search_users_by_name(self, name_keyword: str, limit: int = 10) -> List[UserQnAStats]:
        """
        根据用户名关键词搜索用户

        参数:
            name_keyword: 用户名关键词
            limit: 返回的最大数量

        返回:
            匹配的用户列表，按正确数量排序
        """
        async with self.db.get_session() as session:
            stmt = (
                select(UserQnAStats)
                .where(UserQnAStats.user_name.contains(name_keyword))
                .order_by(desc(UserQnAStats.correct_count), UserQnAStats.updated_at)
                .limit(limit)
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())

    # 获取总用户数量
    async def get_user_total_count(self) -> int:
        """获取总用户数量"""
        async with self.db.get_session() as session:
            stmt = select(func.count()).select_from(UserQnAStats)
            result = await session.execute(stmt)
            return result.scalar_one() or 0

    # 获取提示次数统计
    async def get_tip_stats_summary(self) -> Tuple[int, float]:
        """
        获取提示次数统计摘要

        返回:
            (总提示次数, 平均每用户提示次数)
        """
        async with self.db.get_session() as session:
            # 总提示次数
            total_tips_stmt = select(func.sum(UserQnAStats.tip_count))
            total_tips_result = await session.execute(total_tips_stmt)
            total_tips = total_tips_result.scalar_one() or 0

            # 总用户数
            total_users_stmt = select(func.count()).select_from(UserQnAStats)
            total_users_result = await session.execute(total_users_stmt)
            total_users = total_users_result.scalar_one() or 0

            # 平均提示次数
            avg_tips = total_tips / total_users if total_users > 0 else 0

            return total_tips, avg_tips

    # 删除用户统计记录
    async def delete_user_stats(self, user_id: str) -> bool:
        """删除用户统计记录"""
        async with self.db.get_session() as session:
            stmt = select(UserQnAStats).where(UserQnAStats.user_id == user_id)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if record:
                await session.delete(record)
                return True
            return False

    # 批量获取多个用户的统计信息
    async def get_user_stats_by_ids(self, user_ids: List[str]) -> List[UserQnAStats]:
        """批量获取多个用户的统计信息"""
        if not user_ids:
            return []

        async with self.db.get_session() as session:
            stmt = select(UserQnAStats).where(UserQnAStats.user_id.in_(user_ids))
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ========== 信息获取操作 ==========

    # 获取正确个数排行榜
    async def get_correct_answers_leaderboard(self, limit: int = 10, offset: int = 0) -> List[UserQnAStats]:
        """
        获取正确个数排行榜

        参数:
            limit: 返回的用户数量
            offset: 偏移量（用于分页）

        返回:
            按正确个数降序排列的用户列表
        """
        async with self.db.get_session() as session:
            stmt = (
                select(UserQnAStats)
                .order_by(desc(UserQnAStats.correct_count), UserQnAStats.updated_at)
                .offset(offset)
                .limit(limit)
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())

    # 重置用户答题数据
    async def reset_user_stats(self, user_id: str):
        """重置用户答题数据"""
        async with self.db.get_session() as session:
            stmt = (
                update(UserQnAStats)
                .where(UserQnAStats.user_id == user_id)
                .values(
                    correct_count=0,
                    wrong_count=0,
                    tip_count=0,
                    updated_at=datetime.now()
                )
            )
            await session.execute(stmt)
            await session.commit()

    # 重置所有用户的答题数据
    async def reset_all_stats(self):
        """重置所有用户的答题数据"""
        async with self.db.get_session() as session:
            stmt = (
                update(UserQnAStats)
                .values(
                    correct_count=0,
                    wrong_count=0,
                    tip_count=0,
                    updated_at=datetime.now()
                )
            )
            await session.execute(stmt)
            await session.commit()

    # 获取错误个数排行榜
    async def get_wrong_answers_leaderboard(self, limit: int = 10, offset: int = 0) -> List[UserQnAStats]:
        """
        获取错误个数排行榜

        参数:
            limit: 返回的用户数量
            offset: 偏移量（用于分页）

        返回:
            按错误个数降序排列的用户列表
        """
        async with self.db.get_session() as session:
            stmt = (
                select(UserQnAStats)
                .order_by(desc(UserQnAStats.wrong_count), UserQnAStats.updated_at)
                .offset(offset)
                .limit(limit)
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())

    # 获取提示次数排行榜
    async def get_hints_usage_leaderboard(self, limit: int = 10, offset: int = 0) -> List[UserQnAStats]:
        """
        获取提示次数排行榜

        参数:
            limit: 返回的用户数量
            offset: 偏移量（用于分页）

        返回:
            按提示次数降序排列的用户列表
        """
        async with self.db.get_session() as session:
            stmt = (
                select(UserQnAStats)
                .order_by(desc(UserQnAStats.tip_count), UserQnAStats.updated_at)
                .offset(offset)
                .limit(limit)
            )

            result = await session.execute(stmt)
            return list(result.scalars().all())

    # 获取用户个人信息及在各种排行榜中的排名
    async def get_user_profile_with_rank(self, user_id: str) -> Tuple[Optional[UserQnAStats], dict]:
        """
        获取用户个人信息及在各种排行榜中的排名

        参数:
            user_id: 用户ID

        返回:
            (用户数据, 排名信息字典)
            如果用户不存在: (None, {})
        """
        async with self.db.get_session() as session:
            # 获取用户数据
            user_stats = await self.get_user_stats_only(session, user_id)
            if not user_stats:
                return None, {}

            # 计算正确个数排名
            correct_rank_stmt = select(
                func.count().label('rank')
            ).where(
                and_(
                    UserQnAStats.correct_count > user_stats.correct_count,
                    UserQnAStats.user_id != user_id
                )
            )
            correct_rank_result = await session.execute(correct_rank_stmt)
            correct_rank = (correct_rank_result.scalar_one() or 0) + 1

            # 计算错误个数排名
            wrong_rank_stmt = select(
                func.count().label('rank')
            ).where(
                and_(
                    UserQnAStats.wrong_count > user_stats.wrong_count,
                    UserQnAStats.user_id != user_id
                )
            )
            wrong_rank_result = await session.execute(wrong_rank_stmt)
            wrong_rank = (wrong_rank_result.scalar_one() or 0) + 1

            # 计算提示次数排名
            tip_rank_stmt = select(
                func.count().label('rank')
            ).where(
                and_(
                    UserQnAStats.tip_count > user_stats.tip_count,
                    UserQnAStats.user_id != user_id
                )
            )
            tip_rank_result = await session.execute(tip_rank_stmt)
            tip_rank = (tip_rank_result.scalar_one() or 0) + 1

            # 获取总用户数
            total_stmt = select(func.count()).select_from(UserQnAStats)
            total_result = await session.execute(total_stmt)
            total_users = total_result.scalar_one() or 0

            # 计算准确率（如果答过题）
            total_answers = user_stats.correct_count + user_stats.wrong_count
            accuracy = (user_stats.correct_count / total_answers * 100) if total_answers > 0 else 0

            rank_info = {
                'correct_rank': correct_rank,
                'wrong_rank': wrong_rank,
                'tip_rank': tip_rank,
                'total_users': total_users,
                'accuracy': accuracy,
                'total_answers': total_answers
            }

            return user_stats, rank_info

    # 获取排行榜概要信息
    async def get_leaderboard_summary(self) -> dict:
        """
        获取排行榜概要信息

        返回:
            包含排行榜统计信息的字典
        """
        async with self.db.get_session() as session:
            # 获取总用户数
            total_users_stmt = select(func.count()).select_from(UserQnAStats)
            total_users_result = await session.execute(total_users_stmt)
            total_users = total_users_result.scalar_one() or 0

            # 获取总正确数
            total_correct_stmt = select(func.sum(UserQnAStats.correct_count))
            total_correct_result = await session.execute(total_correct_stmt)
            total_correct = total_correct_result.scalar_one() or 0

            # 获取总错误数
            total_wrong_stmt = select(func.sum(UserQnAStats.wrong_count))
            total_wrong_result = await session.execute(total_wrong_stmt)
            total_wrong = total_wrong_result.scalar_one() or 0

            # 获取总提示次数
            total_tips_stmt = select(func.sum(UserQnAStats.tip_count))
            total_tips_result = await session.execute(total_tips_stmt)
            total_tips = total_tips_result.scalar_one() or 0

            # 获取平均正确数
            avg_correct = total_correct / total_users if total_users > 0 else 0

            return {
                'total_users': total_users,
                'total_correct': total_correct,
                'total_wrong': total_wrong,
                'total_tips': total_tips,
                'avg_correct': avg_correct,
                'total_questions': total_correct + total_wrong
            }

class MatchRepo:
    """比赛数据仓库"""

    def __init__(self, db_manager: DBManager):
        self.db = db_manager

    # 创建新比赛
    async def create_match(self, group_id: str, match_name: str, question_limit: int = 0, time_limit: int = 0) -> Match:
        """
        创建新比赛

        参数:
            group_id: 群组ID
            match_name: 比赛名称
            question_limit: 题目数量限制（0表示无限制）
            time_limit: 时间限制（分钟，0表示无限制）

        返回:
            创建的比赛对象
        """
        async with self.db.get_session() as session:
            match = Match(
                group_id=group_id,
                match_name=match_name,
                is_active=True,
                question_limit=question_limit,
                time_limit=time_limit
            )
            session.add(match)
            await session.commit()
            return match

    # 获取活跃比赛
    async def get_active_match(self, group_id: str) -> Optional[Match]:
        """
        获取指定群组的活跃比赛

        参数:
            group_id: 群组ID

        返回:
            活跃的比赛对象，如果不存在则返回None
        """
        async with self.db.get_session() as session:
            stmt = select(Match).where(
                and_(Match.group_id == group_id, Match.is_active)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # 开始比赛
    async def start_match(self, match_id: int):
        """
        开始指定ID的比赛

        参数:
            match_id: 比赛ID
        """
        async with self.db.get_session() as session:
            stmt = select(Match).where(
                Match.match_id == match_id
            )
            result = await session.execute(stmt)
            match = result.scalar_one_or_none()
            if match:
                match.is_active = True
                match.started_at = datetime.now()
                await session.commit()

    # 结束比赛
    async def end_match(self, match_id: int):
        """
        结束指定ID的比赛

        参数:
            match_id: 比赛ID
        """
        async with self.db.get_session() as session:
            stmt = select(Match).where(
                Match.match_id == match_id
            )
            result = await session.execute(stmt)
            match = result.scalar_one_or_none()
            if match:
                match.is_active = False
                match.ended_at = datetime.now()
                await session.commit()

    # 添加参赛者
    async def add_participant(self, match_id: int, user_id: str, user_name: str) -> MatchParticipant:
        """
        向比赛添加参赛者

        参数:
            match_id: 比赛ID
            user_id: 用户ID
            user_name: 用户名称

        返回:
            参赛者对象（如果已存在则返回现有对象）
        """
        async with self.db.get_session() as session:
            stmt = select(MatchParticipant).where(
                and_(
                    MatchParticipant.match_id == match_id,
                    MatchParticipant.user_id == user_id
                )
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                # 同步最新昵称，避免排行榜/名片长期显示旧昵称
                if existing.user_name != user_name:
                    existing.user_name = user_name
                    await session.commit()
                return existing
            participant = MatchParticipant(
                match_id=match_id,
                user_id=user_id,
                user_name=user_name,
            )
            session.add(participant)
            await session.commit()
            return participant

    # 获取参赛者
    async def get_participant(self, match_id: int, user_id: str) -> Optional[MatchParticipant]:
        """
        获取指定比赛的指定参赛者

        参数:
            match_id: 比赛ID
            user_id: 用户ID

        返回:
            参赛者对象，如果不存在则返回None
        """
        async with self.db.get_session() as session:
            stmt = select(MatchParticipant).where(
                and_(
                    MatchParticipant.match_id == match_id,
                    MatchParticipant.user_id == user_id
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    # 获取所有参赛者
    async def get_participants(self, match_id: int) -> List[MatchParticipant]:
        """
        获取指定比赛的所有参赛者

        参数:
            match_id: 比赛ID

        返回:
            参赛者对象列表
        """
        async with self.db.get_session() as session:
            stmt = select(MatchParticipant).where(MatchParticipant.match_id == match_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # 增加参赛者得分
    async def increment_participant_score(self, match_id: int, user_id: str):
        """
        增加参赛者的正确答题数和分数

        参数:
            match_id: 比赛ID
            user_id: 用户ID
        """
        async with self.db.get_session() as session:
            stmt = select(MatchParticipant).where(
                and_(
                    MatchParticipant.match_id == match_id,
                    MatchParticipant.user_id == user_id
                )
            )
            result = await session.execute(stmt)
            participant = result.scalar_one_or_none()
            if participant:
                participant.correct_count += 1
                participant.score = participant.correct_count - participant.wrong_count / 3.0
                await session.commit()

    # 增加参赛者错误数
    async def increment_participant_wrong(self, match_id: int, user_id: str):
        """
        增加参赛者的错误答题数并更新分数

        参数:
            match_id: 比赛ID
            user_id: 用户ID
        """
        async with self.db.get_session() as session:
            stmt = select(MatchParticipant).where(
                and_(
                    MatchParticipant.match_id == match_id,
                    MatchParticipant.user_id == user_id
                )
            )
            result = await session.execute(stmt)
            participant = result.scalar_one_or_none()
            if participant:
                participant.wrong_count += 1
                participant.score = participant.correct_count - participant.wrong_count / 3.0
                await session.commit()

    # 保存荣誉记录
    async def save_honor(self, user_id: str, match_id: int, match_name: str, rank: int, correct_count: int, wrong_count: int = 0, score: float = 0.0):
        """
        保存用户的比赛荣誉记录

        参数:
            user_id: 用户ID
            match_id: 比赛ID
            match_name: 比赛名称
            rank: 排名
            correct_count: 正确答题数
            wrong_count: 错误答题数（默认为0）
            score: 最终得分（默认为0.0）
        """
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        medal = medals.get(rank, f"{rank}名")
        async with self.db.get_session() as session:
            # match_id=0 为“虚拟比赛ID”（手动授予荣誉），不适用按 match_id 去重
            if match_id != 0:
                existing_stmt = select(MatchHonor).where(
                    and_(MatchHonor.user_id == user_id, MatchHonor.match_id == match_id)
                )
                result = await session.execute(existing_stmt)
                existing_list = list(result.scalars().all())

                if existing_list:
                    keep = existing_list[0]
                    keep.match_name = match_name
                    keep.rank = rank
                    keep.correct_count = correct_count
                    keep.wrong_count = wrong_count
                    keep.score = score
                    keep.medal = medal

                    # 兼容历史重复数据：清理多余的重复荣誉记录
                    for extra in existing_list[1:]:
                        try:
                            session.delete(extra)
                        except Exception:
                            pass

                    await session.commit()
                    return

            honor = MatchHonor(
                user_id=user_id, match_id=match_id, match_name=match_name,
                rank=rank, correct_count=correct_count, wrong_count=wrong_count,
                score=score, medal=medal
            )
            session.add(honor)
            await session.commit()

    # 获取用户荣誉
    async def get_user_honors(self, user_id: str) -> List[MatchHonor]:
        """
        获取用户的荣誉记录

        参数:
            user_id: 用户ID

        返回:
            荣誉记录列表，按排名降序排列
        """
        async with self.db.get_session() as session:
            stmt = select(MatchHonor).where(MatchHonor.user_id == user_id).order_by(desc(MatchHonor.rank))
            result = await session.execute(stmt)
            honors = list(result.scalars().all())

            # 兼容历史数据：同一场比赛可能被重复写入荣誉，名片展示时去重
            deduped: list[MatchHonor] = []
            seen_match_ids: set[int] = set()
            seen_virtual: set[tuple] = set()
            for h in honors:
                mid = getattr(h, "match_id", 0) or 0
                if mid != 0:
                    if int(mid) in seen_match_ids:
                        continue
                    seen_match_ids.add(int(mid))
                else:
                    key = (
                        str(getattr(h, "match_name", "") or ""),
                        int(getattr(h, "rank", 0) or 0),
                        int(getattr(h, "correct_count", 0) or 0),
                        int(getattr(h, "wrong_count", 0) or 0),
                        float(getattr(h, "score", 0.0) or 0.0),
                    )
                    if key in seen_virtual:
                        continue
                    seen_virtual.add(key)
                deduped.append(h)

            return deduped

    # 重置用户荣誉
    async def reset_user_honors(self, user_id: str):
        """
        重置指定用户的所有荣誉数据

        参数:
            user_id: 用户ID
        """
        async with self.db.get_session() as session:
            stmt = delete(MatchHonor).where(MatchHonor.user_id == user_id)
            await session.execute(stmt)
            await session.commit()

    # 重置所有荣誉
    async def reset_all_honors(self):
        """
        重置所有用户的荣誉数据
        """
        async with self.db.get_session() as session:
            stmt = delete(MatchHonor)
            await session.execute(stmt)
            await session.commit()
