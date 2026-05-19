import logging

import pytest

from astrbot.core.log import LogManager


@pytest.fixture(autouse=True)
def restore_log_manager_sinks():
    old_file_sink_id = LogManager._file_sink_id
    old_trace_sink_id = LogManager._trace_sink_id
    try:
        yield
    finally:
        LogManager._file_sink_id = old_file_sink_id
        LogManager._trace_sink_id = old_trace_sink_id


def test_invalid_new_file_sink_keeps_existing_sink(monkeypatch):
    removed_sink_ids = []
    test_logger = logging.getLogger("astrbot.test.runtime")
    LogManager._file_sink_id = 10

    def fail_add_file_sink(**kwargs):
        raise OSError("path is not writable")

    monkeypatch.setattr(LogManager, "_add_file_sink", fail_add_file_sink)
    monkeypatch.setattr(LogManager, "_remove_sink", removed_sink_ids.append)

    LogManager._replace_file_sink(
        logger=test_logger,
        enable_file=True,
        file_path="bad/path/astrbot.log",
        max_mb=20,
    )

    assert LogManager._file_sink_id == 10
    assert removed_sink_ids == []


def test_successful_file_sink_replace_removes_old_sink(monkeypatch):
    removed_sink_ids = []
    test_logger = logging.getLogger("astrbot.test.runtime")
    LogManager._file_sink_id = 10

    monkeypatch.setattr(LogManager, "_add_file_sink", lambda **kwargs: 11)
    monkeypatch.setattr(LogManager, "_remove_sink", removed_sink_ids.append)

    LogManager._replace_file_sink(
        logger=test_logger,
        enable_file=True,
        file_path="logs/astrbot.log",
        max_mb=20,
    )

    assert LogManager._file_sink_id == 11
    assert removed_sink_ids == [10]


def test_invalid_new_trace_sink_keeps_existing_sink(monkeypatch):
    removed_sink_ids = []
    LogManager._trace_sink_id = 20

    def fail_add_trace_sink(**kwargs):
        raise OSError("path is not writable")

    monkeypatch.setattr(LogManager, "_add_file_sink", fail_add_trace_sink)
    monkeypatch.setattr(LogManager, "_remove_sink", removed_sink_ids.append)

    LogManager._replace_trace_sink(
        enable=True,
        path="bad/path/astrbot.trace.log",
        max_mb=20,
    )

    assert LogManager._trace_sink_id == 20
    assert removed_sink_ids == []


def test_disabling_trace_sink_removes_existing_sink(monkeypatch):
    removed_sink_ids = []
    LogManager._trace_sink_id = 20

    monkeypatch.setattr(LogManager, "_remove_sink", removed_sink_ids.append)

    LogManager._replace_trace_sink(
        enable=False,
        path="logs/astrbot.trace.log",
        max_mb=20,
    )

    assert LogManager._trace_sink_id is None
    assert removed_sink_ids == [20]
