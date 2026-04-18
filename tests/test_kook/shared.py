import json
from unittest.mock import AsyncMock, MagicMock
from unittest.mock import AsyncMock


import aiohttp
from astrbot.api.platform import AstrBotMessage, MessageType
from astrbot.core.message.components import (
    File,
    Record,
)


from pathlib import Path

CURRENT_DIR = Path(__file__).parent
TEST_DATA_DIR = CURRENT_DIR / "data"


class KookEventDataPath:
    GROUP_MESSAGE_WITH_MENTION = (
        TEST_DATA_DIR / "kook_ws_event_group_message_with_mention.json"
    )
    GROUP_MESSAGE = TEST_DATA_DIR / "kook_ws_event_group_message.json"
    HELLO = TEST_DATA_DIR / "kook_ws_event_hello.json"
    MESSAGE_WITH_CARD_1 = TEST_DATA_DIR / "kook_ws_event_message_with_card_1.json"
    MESSAGE_WITH_CARD_2 = TEST_DATA_DIR / "kook_ws_event_message_with_card_2.json"
    PING = TEST_DATA_DIR / "kook_ws_event_ping.json"
    PONG = TEST_DATA_DIR / "kook_ws_event_pong.json"
    PRIVATE_MESSAGE = TEST_DATA_DIR / "kook_ws_event_private_message.json"
    PRIVATE_SYSTEM_MESSAGE = TEST_DATA_DIR / "kook_ws_event_private_system_message.json"
    RECONNECT_ERR = TEST_DATA_DIR / "kook_ws_event_reconnect_err.json"
    RESUME_ACK = TEST_DATA_DIR / "kook_ws_event_resume_ack.json"
    RESUME = TEST_DATA_DIR / "kook_ws_event_resume.json"
    GROUP_SYSTEM_MESSAGE_UPDATE_ROLE = TEST_DATA_DIR / "kook_ws_event_group_system_message_update_role.json"


class KookApiDataPath:
    USER_ME = TEST_DATA_DIR / "kook_api_response_user_me.json"
    USER_VIEW = TEST_DATA_DIR / "kook_api_response_user_view.json"


def mock_kook_client(upload_asset_return: str, send_text_return: str):
    client = MagicMock()

    client.upload_asset = AsyncMock(return_value=upload_asset_return)
    client.send_text = AsyncMock(return_value=send_text_return)
    return client


def mock_http_client(
    http_method: str = "get",
    return_value: str | dict | list | None = None,
    status: int = 200,
):
    """Mock aiohttp ClientSession"""

    if isinstance(return_value, (dict, list)):
        response_text = json.dumps(return_value)
    else:
        response_text = return_value or "{}"

    mock_response = MagicMock()
    mock_response.status = status
    mock_response.text = AsyncMock(return_value=response_text)
    mock_response.json = AsyncMock(
        return_value=json.loads(response_text) if response_text else {}
    )
    mock_response.read = AsyncMock(return_value=response_text.encode())
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    mock_session = MagicMock()

    async def mock_method(*args, **kwargs):
        return mock_response

    setattr(mock_session, http_method.lower(), mock_method)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    mock_session.close = AsyncMock()

    return mock_session


def mock_file_message(input: str):
    message = MagicMock(spec=File)
    message.get_file = AsyncMock(return_value=input)
    return message


def mock_record_message(input: str):
    message = MagicMock(spec=Record)
    message.text = input
    message.convert_to_file_path = AsyncMock(return_value=input)
    return message


def mock_astrbot_message():
    message = AstrBotMessage()
    message.type = MessageType.OTHER_MESSAGE
    message.group_id = "test"
    message.session_id = "test"
    message.message_id = "test"
    return message


def mock_kook_roles_record(bot_id: str, http_client: aiohttp.ClientSession):
    instance = AsyncMock()
    instance.has_role_in_channel = AsyncMock(return_value=True)
    return instance
