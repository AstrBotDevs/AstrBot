import aiosqlite
import os
import time
from ..po import Platform, Stats, Conversation
from .. import BaseDatabase
from typing import Tuple, List, Dict, Any


class SQLiteDatabase(BaseDatabase):
    def __init__(self, db_path: str) -> None:
        super().__init__()
        self.db_path = db_path
        self.conn = None

    async def initialize(self) -> None:
        """初始化数据库连接和表结构"""
        with open(os.path.dirname(__file__) + "/schemas/sqlite_init.sql", "r") as f:
            sql = f.read()

        # 初始化数据库
        await self._ensure_connection()
        async with self.conn.cursor() as c:
            await c.executescript(sql)
            await self.conn.commit()

        # 检查 webchat_conversation 的 title 字段是否存在
        async with self.conn.cursor() as c:
            await c.execute(
                """
                PRAGMA table_info(webchat_conversation)
                """
            )
            res = await c.fetchall()
            has_title = False
            has_persona_id = False
            for row in res:
                if row[1] == "title":
                    has_title = True
                if row[1] == "persona_id":
                    has_persona_id = True
            if not has_title:
                await c.execute(
                    """
                    ALTER TABLE webchat_conversation ADD COLUMN title TEXT;
                    """
                )
                await self.conn.commit()
            if not has_persona_id:
                await c.execute(
                    """
                    ALTER TABLE webchat_conversation ADD COLUMN persona_id TEXT;
                    """
                )
                await self.conn.commit()

    async def _get_conn(self, db_path: str) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(db_path)
        conn.text_factory = str
        return conn

    async def _ensure_connection(self):
        """确保数据库连接有效"""
        if self.conn is None:
            self.conn = await self._get_conn(self.db_path)
        return self.conn

    async def _exec_sql(self, sql: str, params: Tuple = None):
        await self._ensure_connection()

        async with self.conn.cursor() as c:
            if params:
                await c.execute(sql, params)
            else:
                await c.execute(sql)
            await self.conn.commit()

    async def insert_platform_metrics(self, metrics: dict):
        for k, v in metrics.items():
            await self._exec_sql(
                """
                INSERT INTO platform(name, count, timestamp) VALUES (?, ?, ?)
                """,
                (k, v, int(time.time())),
            )

    async def insert_llm_metrics(self, metrics: dict):
        for k, v in metrics.items():
            await self._exec_sql(
                """
                INSERT INTO llm(name, count, timestamp) VALUES (?, ?, ?)
                """,
                (k, v, int(time.time())),
            )

    async def get_base_stats(self, offset_sec: int = 86400) -> Stats:
        """获取 offset_sec 秒前到现在的基础统计数据"""
        where_clause = f" WHERE timestamp >= {int(time.time()) - offset_sec}"

        await self._ensure_connection()

        platform = []
        async with self.conn.cursor() as c:
            await c.execute(
                """
                SELECT * FROM platform
                """
                + where_clause
            )

            async for row in c:
                platform.append(Platform(*row))

        return Stats(platform, [], [])

    async def get_total_message_count(self) -> int:
        await self._ensure_connection()

        async with self.conn.cursor() as c:
            await c.execute(
                """
                SELECT SUM(count) FROM platform
                """
            )
            res = await c.fetchone()
            return res[0] if res[0] is not None else 0

    async def get_grouped_base_stats(self, offset_sec: int = 86400) -> Stats:
        """获取 offset_sec 秒前到现在的基础统计数据(合并)"""
        where_clause = f" WHERE timestamp >= {int(time.time()) - offset_sec}"

        await self._ensure_connection()

        platform = []
        async with self.conn.cursor() as c:
            await c.execute(
                """
                SELECT name, SUM(count), timestamp FROM platform
                """
                + where_clause
                + " GROUP BY name"
            )

            async for row in c:
                platform.append(Platform(*row))

        return Stats(platform, [], [])

    async def get_conversation_by_user_id(self, user_id: str, cid: str) -> Conversation:
        await self._ensure_connection()

        async with self.conn.cursor() as c:
            await c.execute(
                """
                SELECT * FROM webchat_conversation WHERE user_id = ? AND cid = ?
                """,
                (user_id, cid),
            )

            res = await c.fetchone()
            if not res:
                return None

            return Conversation(*res)

    async def new_conversation(self, user_id: str, cid: str):
        history = "[]"
        updated_at = int(time.time())
        created_at = updated_at
        await self._exec_sql(
            """
            INSERT INTO webchat_conversation(user_id, cid, history, updated_at, created_at) VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, cid, history, updated_at, created_at),
        )

    async def get_conversations(self, user_id: str) -> Tuple:
        await self._ensure_connection()

        conversations = []
        async with self.conn.cursor() as c:
            await c.execute(
                """
                SELECT cid, created_at, updated_at, title, persona_id FROM webchat_conversation WHERE user_id = ? ORDER BY updated_at DESC
                """,
                (user_id,),
            )

            async for row in c:
                cid = row[0]
                created_at = row[1]
                updated_at = row[2]
                title = row[3]
                persona_id = row[4]
                conversations.append(
                    Conversation(
                        "", cid, "[]", created_at, updated_at, title, persona_id
                    )
                )
        return conversations

    async def update_conversation(self, user_id: str, cid: str, history: str):
        """更新对话，并且同时更新时间"""
        updated_at = int(time.time())
        await self._exec_sql(
            """
            UPDATE webchat_conversation SET history = ?, updated_at = ? WHERE user_id = ? AND cid = ?
            """,
            (history, updated_at, user_id, cid),
        )

    async def update_conversation_title(self, user_id: str, cid: str, title: str):
        await self._exec_sql(
            """
            UPDATE webchat_conversation SET title = ? WHERE user_id = ? AND cid = ?
            """,
            (title, user_id, cid),
        )

    async def update_conversation_persona_id(
        self, user_id: str, cid: str, persona_id: str
    ):
        await self._exec_sql(
            """
            UPDATE webchat_conversation SET persona_id = ? WHERE user_id = ? AND cid = ?
            """,
            (persona_id, user_id, cid),
        )

    async def delete_conversation(self, user_id: str, cid: str):
        await self._exec_sql(
            """
            DELETE FROM webchat_conversation WHERE user_id = ? AND cid = ?
            """,
            (user_id, cid),
        )

    async def get_all_conversations(
        self, page: int = 1, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], int]:
        """获取所有对话，支持分页，按更新时间降序排序"""
        await self._ensure_connection()

        try:
            # 获取总记录数
            async with self.conn.cursor() as c:
                await c.execute("""
                    SELECT COUNT(*) FROM webchat_conversation
                """)
                total_count = (await c.fetchone())[0]

                # 计算偏移量
                offset = (page - 1) * page_size

                # 获取分页数据，按更新时间降序排序
                await c.execute(
                    """
                    SELECT user_id, cid, created_at, updated_at, title, persona_id
                    FROM webchat_conversation
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?
                """,
                    (page_size, offset),
                )

                rows = await c.fetchall()

                conversations = []

                for row in rows:
                    user_id, cid, created_at, updated_at, title, persona_id = row
                    # 确保 cid 是字符串类型且至少有8个字符，否则使用一个默认值
                    safe_cid = str(cid) if cid else "unknown"
                    display_cid = safe_cid[:8] if len(safe_cid) >= 8 else safe_cid

                    conversations.append(
                        {
                            "user_id": user_id or "",
                            "cid": safe_cid,
                            "title": title or f"对话 {display_cid}",
                            "persona_id": persona_id or "",
                            "created_at": created_at or 0,
                            "updated_at": updated_at or 0,
                        }
                    )

                return conversations, total_count

        except Exception as _:
            # 返回空列表和0，确保即使出错也有有效的返回值
            return [], 0

    async def get_filtered_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
        platforms: List[str] = None,
        message_types: List[str] = None,
        search_query: str = None,
        exclude_ids: List[str] = None,
        exclude_platforms: List[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """获取筛选后的对话列表"""
        await self._ensure_connection()

        try:
            # 构建查询条件
            where_clauses = []
            params = []

            # 平台筛选
            if platforms and len(platforms) > 0:
                platform_conditions = []
                for platform in platforms:
                    platform_conditions.append("user_id LIKE ?")
                    params.append(f"{platform}:%")

                if platform_conditions:
                    where_clauses.append(f"({' OR '.join(platform_conditions)})")

            # 消息类型筛选
            if message_types and len(message_types) > 0:
                message_type_conditions = []
                for msg_type in message_types:
                    message_type_conditions.append("user_id LIKE ?")
                    params.append(f"%:{msg_type}:%")

                if message_type_conditions:
                    where_clauses.append(f"({' OR '.join(message_type_conditions)})")

            # 搜索关键词
            if search_query:
                search_query = search_query.encode("unicode_escape").decode("utf-8")
                where_clauses.append(
                    "(title LIKE ? OR user_id LIKE ? OR cid LIKE ? OR history LIKE ?)"
                )
                search_param = f"%{search_query}%"
                params.extend([search_param, search_param, search_param, search_param])

            # 排除特定用户ID
            if exclude_ids and len(exclude_ids) > 0:
                for exclude_id in exclude_ids:
                    where_clauses.append("user_id NOT LIKE ?")
                    params.append(f"{exclude_id}%")

            # 排除特定平台
            if exclude_platforms and len(exclude_platforms) > 0:
                for exclude_platform in exclude_platforms:
                    where_clauses.append("user_id NOT LIKE ?")
                    params.append(f"{exclude_platform}:%")

            # 构建完整的 WHERE 子句
            where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            async with self.conn.cursor() as c:
                # 构建计数查询
                count_sql = f"SELECT COUNT(*) FROM webchat_conversation{where_sql}"

                # 获取总记录数
                await c.execute(count_sql, params)
                total_count = (await c.fetchone())[0]

                # 计算偏移量
                offset = (page - 1) * page_size

                # 构建分页数据查询
                data_sql = f"""
                    SELECT user_id, cid, created_at, updated_at, title, persona_id
                    FROM webchat_conversation
                    {where_sql}
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?
                """
                query_params = params + [page_size, offset]

                # 获取分页数据
                await c.execute(data_sql, query_params)
                rows = await c.fetchall()

                conversations = []

                for row in rows:
                    user_id, cid, created_at, updated_at, title, persona_id = row
                    # 确保 cid 是字符串类型，否则使用一个默认值
                    safe_cid = str(cid) if cid else "unknown"
                    display_cid = safe_cid[:8] if len(safe_cid) >= 8 else safe_cid

                    conversations.append(
                        {
                            "user_id": user_id or "",
                            "cid": safe_cid,
                            "title": title or f"对话 {display_cid}",
                            "persona_id": persona_id or "",
                            "created_at": created_at or 0,
                            "updated_at": updated_at or 0,
                        }
                    )

                return conversations, total_count

        except Exception as _:
            # 返回空列表和0，确保即使出错也有有效的返回值
            return [], 0

    async def close(self):
        """关闭数据库连接"""
        if self.conn is not None and not self.conn.closed:
            await self.conn.close()
            self.conn = None

    async def reconnect(self):
        """重新连接数据库"""
        await self.close()
        await self._ensure_connection()
