from fastapi.responses import JSONResponse, Response

from astrbot.core.platform.webhook_server import webhook_response_from_result


def test_webhook_response_preserves_plain_string():
    response = webhook_response_from_result("success")

    assert isinstance(response, Response)
    assert response.body == b"success"


def test_webhook_response_preserves_tuple_headers():
    response = webhook_response_from_result(
        ("accepted", 202, {"Content-Type": "text/plain"})
    )

    assert isinstance(response, Response)
    assert response.status_code == 202
    assert response.media_type == "text/plain"
    assert response.body == b"accepted"


def test_webhook_response_keeps_json_for_dict():
    response = webhook_response_from_result({"ok": True})

    assert isinstance(response, JSONResponse)
