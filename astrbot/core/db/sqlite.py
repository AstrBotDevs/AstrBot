import sqlite3
import os
import time
from astrbot.core.db.po import Platform, Stats, LLMHistory, ATRIVision, Conversation
from . import BaseDatabase
from typing import Tuple


class SQLiteDatabase(BaseDatabase):
    def __init__(self, db_path: str) -> None:
        super().__init__()
        self.db_path = db_path

        with open(os.path.dirname(__file__) + "/sqlite_init.sql", "r") as f:
            sql = f.read()

        # 初始化数据库
        self.conn = self._get_conn(self.db_path)
        c = self.conn.cursor()
        c.executescript(sql)
        self.conn.commit()

        # 检查 webchat_conversation 的 title 字段是否存在
        c.execute(
            """
            PRAGMA table_info(webchat_conversation)
            """
        )
        res = c.fetchall()
        has_title = False
        has_persona_id = False
        for row in res:
            if row[1] == "title":
                has_title = True
            if row[1] == "persona_id":
                has_persona_id = True
        if not has_title:
            c.execute(
                """
                ALTER TABLE webchat_conversation ADD COLUMN title TEXT;
                """
            )
            self.conn.commit()
        if not has_persona_id:
            c.execute(
                """
                ALTER TABLE webchat_conversation ADD COLUMN persona_id TEXT;
                """
            )
            self.conn.commit()

        c.close()

    def _get_conn(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.text_factory = str
        return conn

    def _exec_sql(self, sql: str, params: Tuple = None):
        conn = self.conn
        try:
            c = self.conn.cursor()
        except sqlite3.ProgrammingError:
            conn = self._get_conn(self.db_path)
            c = conn.cursor()

        if params:
            c.execute(sql, params)
            c.close()
        else:
            c.execute(sql)
            c.close()

        conn.commit()

    def insert_platform_metrics(self, metrics: dict):
        for k, v in metrics.items():
            self._exec_sql(
                """
                INSERT INTO platform(name, count, timestamp) VALUES (?, ?, ?)
                """,
                (k, v, int(time.time())),
            )

    def insert_plugin_metrics(self, metrics: dict):
        pass

    def insert_command_metrics(self, metrics: dict):
        for k, v in metrics.items():
            self._exec_sql(
                """
                INSERT INTO command(name, count, timestamp) VALUES (?, ?, ?)
                """,
                (k, v, int(time.time())),
            )

    def insert_llm_metrics(self, metrics: dict):
        for k, v in metrics.items():
            self._exec_sql(
                """
                INSERT INTO llm(name, count, timestamp) VALUES (?, ?, ?)
                """,
                (k, v, int(time.time())),
            )

    def update_llm_history(self, session_id: str, content: str, provider_type: str):
        res = self.get_llm_history(session_id, provider_type)
        if res:
            self._exec_sql(
                """
                UPDATE llm_history SET content = ? WHERE session_id = ? AND provider_type = ?
                """,
                (content, session_id, provider_type),
            )
        else:
            self._exec_sql(
                """
                INSERT INTO llm_history(provider_type, session_id, content) VALUES (?, ?, ?)
                """,
                (provider_type, session_id, content),
            )

    def get_llm_history(
        self, session_id: str = None, provider_type: str = None
    ) -> Tuple:
        try:
            c = self.conn.cursor()
        except sqlite3.ProgrammingError:
            c = self._get_conn(self.db_path).cursor()

        where_clause = ""
        if session_id or provider_type:
            where_clause += " WHERE "
            has = False
            if session_id:
                where_clause += f"session_id = '{session_id}'"
                has = True
            if provider_type:
                if has:
                    where_clause += " AND "
                where_clause += f"provider_type = '{provider_type}'"

        c.execute(
            """
            SELECT * FROM llm_history
            """
            + where_clause
        )
        res = c.fetchall()
        histories = []
        for row in res:
            histories.append(LLMHistory(*row))
        c.close()
        return histories

    def get_base_stats(self, offset_sec: int = 86400) -> Stats:
        """获取 offset_sec 秒前到现在的基础统计数据"""
        where_clause = f" WHERE timestamp >= {int(time.time()) - offset_sec}"

        try:
            c = self.conn.cursor()
        except sqlite3.ProgrammingError:
            c = self._get_conn(self.db_path).cursor()

        c.execute(
            """
            SELECT * FROM platform
            """
            + where_clause
        )

        platform = []
        for row in c.fetchall():
            platform.append(Platform(*row))

        # c.execute(
        #     '''
        #     SELECT * FROM command
        #     ''' + where_clause
        # )

        # command = []
        # for row in c.fetchall():
        #     command.append(Command(*row))

        # c.execute(
        #     '''
        #     SELECT * FROM llm
        #     ''' + where_clause
        # )

        # llm = []
        # for row in c.fetchall():
        #     llm.append(Provider(*row))

        c.close()

        return Stats(platform, [], [])

    def get_total_message_count(self) -> int:
        try:
            c = self.conn.cursor()
        except sqlite3.ProgrammingError:
            c = self._get_conn(self.db_path).cursor()

        c.execute(
            """
            SELECT SUM(count) FROM platform
            """
        )
        res = c.fetchone()
        c.close()
        return res[0]

    def get_grouped_base_stats(self, offset_sec: int = 86400) -> Stats:
        """获取 offset_sec 秒前到现在的基础统计数据(合并)"""
        where_clause = f" WHERE timestamp >= {int(time.time()) - offset_sec}"

        try:
            c = self.conn.cursor()
        except sqlite3.ProgrammingError:
            c = self._get_conn(self.db_path).cursor()

        c.execute(
            """
            SELECT name, SUM(count), timestamp FROM platform
            """
            + where_clause
            + " GROUP BY name"
        )

        platform = []
        for row in c.fetchall():
            platform.append(Platform(*row))

        c.close()

        return Stats(platform, [], [])

    def get_conversation_by_user_id(self, user_id: str, cid: str) -> Conversation:
        try:
            c = self.conn.cursor()
        except sqlite3.ProgrammingError:
            c = self._get_conn(self.db_path).cursor()

        c.execute(
            """
            SELECT * FROM webchat_conversation WHERE user_id = ? AND cid = ?
            """,
            (user_id, cid),
        )

        res = c.fetchone()
        c.close()

        if not res:
            return

        return Conversation(*res)

    def new_conversation(self, user_id: str, cid: str):
        history = "[]"
        updated_at = int(time.time())
        created_at = updated_at
        self._exec_sql(
            """
            INSERT INTO webchat_conversation(user_id, cid, history, updated_at, created_at) VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, cid, history, updated_at, created_at),
        )

    def get_conversations(self, user_id: str) -> Tuple:
        try:
            c = self.conn.cursor()
        except sqlite3.ProgrammingError:
            c = self._get_conn(self.db_path).cursor()

        c.execute(
            """
            SELECT cid, created_at, updated_at, title, persona_id FROM webchat_conversation WHERE user_id = ? ORDER BY updated_at DESC
            """,
            (user_id,),
        )

        res = c.fetchall()
        c.close()
        conversations = []
        for row in res:
            cid = row[0]
            created_at = row[1]
            updated_at = row[2]
            title = row[3]
            persona_id = row[4]
            conversations.append(
                Conversation("", cid, "[]", created_at, updated_at, title, persona_id)
            )
        return conversations

    def update_conversation(self, user_id: str, cid: str, history: str):
        """更新对话，并且同时更新时间"""
        updated_at = int(time.time())
        self._exec_sql(
            """
            UPDATE webchat_conversation SET history = ?, updated_at = ? WHERE user_id = ? AND cid = ?
            """,
            (history, updated_at, user_id, cid),
        )

    def update_conversation_title(self, user_id: str, cid: str, title: str):
        self._exec_sql(
            """
            UPDATE webchat_conversation SET title = ? WHERE user_id = ? AND cid = ?
            """,
            (title, user_id, cid),
        )

    def update_conversation_persona_id(self, user_id: str, cid: str, persona_id: str):
        self._exec_sql(
            """
            UPDATE webchat_conversation SET persona_id = ? WHERE user_id = ? AND cid = ?
            """,
            (persona_id, user_id, cid),
        )

    def delete_conversation(self, user_id: str, cid: str):
        self._exec_sql(
            """
            DELETE FROM webchat_conversation WHERE user_id = ? AND cid = ?
            """,
            (user_id, cid),
        )

    def insert_atri_vision_data(self, vision: ATRIVision):
        ts = int(time.time())
        keywords = ",".join(vision.keywords)
        self._exec_sql(
            """
            INSERT INTO atri_vision(id, url_or_path, caption, is_meme, keywords, platform_name, session_id, sender_nickname, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                vision.id,
                vision.url_or_path,
                vision.caption,
                vision.is_meme,
                keywords,
                vision.platform_name,
                vision.session_id,
                vision.sender_nickname,
                ts,
            ),
        )

    def get_atri_vision_data(self) -> Tuple:
        try:
            c = self.conn.cursor()
        except sqlite3.ProgrammingError:
            c = self._get_conn(self.db_path).cursor()

        c.execute(
            """
            SELECT * FROM atri_vision
            """
        )

        res = c.fetchall()
        visions = []
        for row in res:
            visions.append(ATRIVision(*row))
        c.close()
        return visions

    def get_atri_vision_data_by_path_or_id(
        self, url_or_path: str, id: str
    ) -> ATRIVision:
        try:
            c = self.conn.cursor()
        except sqlite3.ProgrammingError:
            c = self._get_conn(self.db_path).cursor()

        c.execute(
            """
            SELECT * FROM atri_vision WHERE url_or_path = ? OR id = ?
            """,
            (url_or_path, id),
        )

        res = c.fetchone()
        c.close()
        if res:
            return ATRIVision(*res)
        return None
