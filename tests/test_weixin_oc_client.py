from astrbot.core.platform.sources.weixin_oc.weixin_oc_client import WeixinOCClient


def test_encrypt_decrypt_cdn_payload_round_trip() -> None:
    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    payload = b"astrbot-weixin-oc-media" * 3

    encrypted = WeixinOCClient.encrypt_cdn_payload(payload, key)

    assert encrypted != payload
    assert WeixinOCClient.decrypt_cdn_payload(encrypted, key) == payload
