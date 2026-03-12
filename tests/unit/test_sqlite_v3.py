from unittest.mock import MagicMock, patch

from astrbot.core.db.migration.sqlite_v3 import SQLiteDatabase


class TestSQLiteV3QueryParameterization:
    def _create_db_with_mock_cursor(self):
        db = SQLiteDatabase(":memory:")
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = (0,)

        conn = MagicMock()
        conn.cursor.return_value = cursor
        db.conn = conn
        return db, cursor

    def test_get_base_stats_uses_bound_parameter(self):
        db, cursor = self._create_db_with_mock_cursor()

        with patch("astrbot.core.db.migration.sqlite_v3.time.time", return_value=1000):
            db.get_base_stats(offset_sec=60)

        sql, params = cursor.execute.call_args.args
        assert (
            " ".join(sql.split())
            == "SELECT * FROM platform WHERE timestamp >= :min_timestamp"
        )
        assert params == {"min_timestamp": 940}

    def test_get_grouped_base_stats_uses_bound_parameter(self):
        db, cursor = self._create_db_with_mock_cursor()

        with patch("astrbot.core.db.migration.sqlite_v3.time.time", return_value=1000):
            db.get_grouped_base_stats(offset_sec=60)

        sql, params = cursor.execute.call_args.args
        assert " ".join(sql.split()) == (
            "SELECT name, SUM(count), timestamp FROM platform "
            "WHERE timestamp >= :min_timestamp GROUP BY name"
        )
        assert params == {"min_timestamp": 940}

    def test_get_filtered_conversations_uses_named_parameters(self):
        db, cursor = self._create_db_with_mock_cursor()

        db.get_filtered_conversations(
            page=2,
            page_size=10,
            platforms=["qq"],
            message_types=["group"],
            search_query="x' OR 1=1 --",
            exclude_ids=["admin"],
            exclude_platforms=["slack"],
        )

        count_sql, count_params = cursor.execute.call_args_list[0].args
        data_sql, data_params = cursor.execute.call_args_list[1].args

        assert ":platform_0" in count_sql
        assert ":message_type_0" in count_sql
        assert ":search_query" in count_sql
        assert ":exclude_id_0" in count_sql
        assert ":exclude_platform_0" in count_sql
        assert "x' OR 1=1 --" not in count_sql
        assert count_params["platform_0"] == "qq:%"
        assert count_params["message_type_0"] == "%:group:%"
        assert count_params["search_query"] == "%x' OR 1=1 --%"
        assert count_params["exclude_id_0"] == "admin%"
        assert count_params["exclude_platform_0"] == "slack:%"

        assert "FROM webchat_conversation WHERE" in data_sql
        assert ":page_size" in data_sql
        assert ":offset" in data_sql
        assert data_params["page_size"] == 10
        assert data_params["offset"] == 10
