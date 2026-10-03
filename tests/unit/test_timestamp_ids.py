from datetime import datetime
from types import SimpleNamespace

from astrbot.core.utils import datetime_utils


def test_generate_timestamp_id_uses_compact_local_time(monkeypatch):
    class FixedDateTime:
        @classmethod
        def now(cls):
            return datetime(2026, 2, 3, 13, 0, 43, 123000)

    monkeypatch.setattr(datetime_utils, "datetime", FixedDateTime)
    monkeypatch.setattr(
        datetime_utils.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="abcd1234567890"),
    )

    assert datetime_utils.generate_timestamp_id() == "20260203130043123_abcd"
