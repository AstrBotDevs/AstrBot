import asyncio
import json
import logging

import pytest

from astrbot.core.log import LogBroker, LogQueueHandler, _RecordEnricherFilter
from astrbot.dashboard.services.log_service import LogService


def test_log_queue_emits_stable_protocol_and_redacts_sensitive_data():
    broker = LogBroker()
    handler = LogQueueHandler(broker)
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        10,
        "token=https://example.test/api?api_key=secret",
        (),
        None,
    )
    record.category = "user_chat"
    record.privacy = "private"
    record.platform = "test"
    record.conversation_id = "umo-1"
    record.sender_id = "sender-1"
    record.summary = "Inbound platform event received"
    _RecordEnricherFilter().filter(record)
    handler.emit(record)

    entry = broker.log_cache[-1]
    assert {
        "category",
        "privacy",
        "event_id",
        "timestamp",
        "platform",
        "conversation_id",
        "sender_id",
        "summary",
    } <= entry.keys()
    assert entry["category"] == "user_chat"
    assert entry["privacy"] == "private"
    assert "secret" not in entry["data"]
    assert entry["event_id"]


def test_log_enricher_normalizes_unknown_fields_and_bounds_summary():
    broker = LogBroker()
    handler = LogQueueHandler(broker)
    handler.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        10,
        "ordinary message",
        (),
        None,
    )
    record.category = "not-a-category"
    record.privacy = "not-a-privacy"
    record.summary = "api_key=secret " * 200
    _RecordEnricherFilter().filter(record)
    handler.emit(record)

    entry = broker.log_cache[-1]
    assert entry["category"] == "system"
    assert entry["privacy"] == "internal"
    assert len(entry["summary"]) <= 512
    assert "secret" not in entry["summary"]



def test_log_service_filters_categories_and_replays_by_event_id():
    broker = LogBroker()
    broker.publish(
        {
            "event_id": "one",
            "time": 1.0,
            "timestamp": 1.0,
            "category": "system",
            "privacy": "internal",
            "level": "INFO",
            "data": "system",
        }
    )
    broker.publish(
        {
            "event_id": "two",
            "time": 2.0,
            "timestamp": 2.0,
            "category": "user_chat",
            "privacy": "private",
            "level": "INFO",
            "data": "chat",
        }
    )
    service = LogService(broker, object())
    assert (
        service.get_log_history(categories={"system"})["logs"][0]["event_id"] == "one"
    )

    async def collect() -> list[dict]:
        events = []
        async for item in service.replay_cached_logs("one"):
            events.append(json.loads(item.split("data: ", 1)[1]))
        return events

    events = asyncio.run(collect())
    assert [event["event_id"] for event in events] == ["two"]


def test_log_service_replays_after_timestamp_when_event_id_is_unknown():
    broker = LogBroker()
    for event_id, timestamp in (("one", 1.0), ("two", 2.0), ("three", 3.0)):
        broker.publish(
            {
                "event_id": event_id,
                "time": timestamp,
                "timestamp": timestamp,
                "category": "system",
                "privacy": "internal",
                "level": "INFO",
                "data": event_id,
            }
        )
    service = LogService(broker, object())

    async def collect() -> list[dict]:
        events = []
        async for item in service.replay_cached_logs("1.5"):
            events.append(json.loads(item.split("data: ", 1)[1]))
        return events

    events = asyncio.run(collect())
    assert [event["event_id"] for event in events] == ["two", "three"]


@pytest.mark.asyncio
async def test_log_stream_filters_live_events_and_unregisters():
    broker = LogBroker()
    service = LogService(broker, object())
    stream = service.stream_log_events(
        None,
        categories={"security"},
        privacy={"internal"},
    )
    pending = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)
    assert len(broker.subscribers) == 1

    broker.publish(
        {
            "event_id": "private-chat",
            "time": 1.0,
            "timestamp": 1.0,
            "category": "user_chat",
            "privacy": "private",
            "level": "INFO",
            "data": "ignored",
        }
    )
    broker.publish(
        {
            "event_id": "security-event",
            "time": 2.0,
            "timestamp": 2.0,
            "category": "security",
            "privacy": "internal",
            "level": "WARNING",
            "data": "allowed",
        }
    )
    event = await asyncio.wait_for(pending, timeout=1)
    payload = json.loads(event.split("data: ", 1)[1])
    assert payload["event_id"] == "security-event"
    assert payload["type"] == "log"
    assert event.startswith("id: security-event\n")

    await stream.aclose()
    assert broker.subscribers == []


@pytest.mark.asyncio
async def test_log_stream_reraises_cancellation():
    broker = LogBroker()
    service = LogService(broker, object())
    stream = service.stream_log_events(None)
    task = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await stream.aclose()
