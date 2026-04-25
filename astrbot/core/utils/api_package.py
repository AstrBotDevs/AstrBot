import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from quart import request


class InvalidSignatureError(Exception):
    pass


def de_package(apikey: str, data: str, noise: str, expiry_date: str, signature: str) -> dict:
    if not data:
        raise InvalidSignatureError("data is empty")
    if not noise:
        raise InvalidSignatureError("noise is empty")
    if not expiry_date:
        raise InvalidSignatureError("expiry_date is empty")
    if not signature:
        raise InvalidSignatureError("signature is empty")

    date = datetime.fromisoformat(expiry_date)
    if date.tzinfo is None:
        date = date.astimezone()
    if date < datetime.now(timezone.utc):
        raise InvalidSignatureError("expiry_date is expired")

    payload = f"{data}{noise}{expiry_date}{apikey}"
    computed = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    if not hmac.compare_digest(computed, signature):
        raise InvalidSignatureError("signature error")

    try:
        decoded_bytes = base64.b64decode(data)
        decoded_str = decoded_bytes.decode("utf-8")
        result = json.loads(decoded_str)
    except Exception as e:
        raise InvalidSignatureError(f"failed to decode data: {e}")

    return result


def en_package(appid: str, apikey: str, data: dict) -> dict:
    encode_data = base64.b64encode(
        json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")
    noise = secrets.token_urlsafe(32)
    expiry_date = (datetime.now().astimezone() + timedelta(days=1)).replace(microsecond=0).isoformat()
    signature = hashlib.sha256(f"{encode_data}{noise}{expiry_date}{apikey}".encode()).hexdigest()

    return {
        "appid": appid,
        "data": encode_data,
        "noise": noise,
        "expiry_date": expiry_date,
        "signature": signature,
        "apikey": apikey,
    }


# 按顺序获取输入参数：json -> form -> query -> header
async def request_input(name: list) -> dict:
    json_data = await request.get_json(silent=True) or {}
    form_data = (await request.form).to_dict() or {}

    return_data = {}
    for item in name:
        if request.method == "POST":
            if item in json_data:
                return_data[item] = json_data.get(item)
                continue
            if item in form_data:
                return_data[item] = form_data[item]
                continue
        if item in request.args:
            return_data[item] = request.args.get(item)
            continue
        if item in request.headers:
            return_data[item] = request.headers.get(item)
            continue
    return return_data
