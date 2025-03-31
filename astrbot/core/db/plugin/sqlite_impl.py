import json
import aiosqlite
import os
from typing import Any
from .plugin_storage import PluginStorage

DBPATH = "data/plugin_data/sqlite/plugin_data.db"


class SQLitePluginStorage(PluginStorage):
    """插件数据的 SQLite 存储实现类。

    该类提供异步方式将插件数据存储到 SQLite 数据库中，支持数据的增删改查操作。
    所有数据以 (plugin, key) 作为复合主键进行索引。
    """

    _instance = None  # Standalone instance of the class
    _db_conn = None
    db_path = None

    def __new__(cls):
        """
        创建或获取 SQLitePluginStorage 的单例实例。
        如果实例已存在，则返回现有实例；否则创建一个新实例。
        数据在 `data/plugin_data/sqlite/plugin_data.db` 下。
        """
        os.makedirs(os.path.dirname(DBPATH), exist_ok=True)
        if cls._instance is None:
            cls._instance = super(SQLitePluginStorage, cls).__new__(cls)
            cls._instance.db_path = DBPATH
        return cls._instance

    async def _init_db(self):
        """初始化数据库连接（只执行一次）"""
        if SQLitePluginStorage._db_conn is None:
            SQLitePluginStorage._db_conn = await aiosqlite.connect(self.db_path)
            await self._setup_db()

    async def _setup_db(self):
        """
        异步初始化数据库。

        创建插件数据表，如果表不存在则创建，表结构包含 plugin、key 和 value 字段，
        其中 plugin 和 key 组合作为主键。
        """
        await self._db_conn.execute("""
            CREATE TABLE IF NOT EXISTS plugin_data (
                plugin TEXT,
                key TEXT,
                value TEXT,
                PRIMARY KEY (plugin, key)
            )
        """)
        await self._db_conn.commit()

    async def set(self, plugin: str, key: str, value: Any):
        """
        异步存储数据。

        将指定插件的键值对存入数据库，如果键已存在则更新值。
        值会被序列化为 JSON 字符串后存储。

        Args:
            plugin: 插件标识符
            key: 数据键名
            value: 要存储的数据值（任意类型，将被 JSON 序列化）
        """
        await self._init_db()
        await self._db_conn.execute(
            "INSERT INTO plugin_data (plugin, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(plugin, key) DO UPDATE SET value = excluded.value",
            (plugin, key, json.dumps(value)),
        )
        await self._db_conn.commit()

    async def get(self, plugin: str, key: str) -> Any:
        """
        异步获取数据。

        从数据库中获取指定插件和键名对应的值，
        返回的值会从 JSON 字符串反序列化为原始数据类型。

        Args:
            plugin: 插件标识符
            key: 数据键名

        Returns:
            Any: 存储的数据值，如果未找到则返回 None
        """
        await self._init_db()
        async with self._db_conn.execute(
            "SELECT value FROM plugin_data WHERE plugin = ? AND key = ?",
            (plugin, key),
        ) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else None

    async def delete(self, plugin: str, key: str):
        """
        异步删除数据。

        从数据库中删除指定插件和键名对应的数据项。

        Args:
            plugin: 插件标识符
            key: 要删除的数据键名
        """
        await self._init_db()
        await self._db_conn.execute(
            "DELETE FROM plugin_data WHERE plugin = ? AND key = ?", (plugin, key)
        )
        await self._db_conn.commit()
