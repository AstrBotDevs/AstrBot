#!/usr/bin/env python
# coding=utf-8
# 文档：https://developer.work.weixin.qq.com/document/path/101039

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
import uvicorn
import os
import logging
import json
import random
import string
import time
import base64
import hashlib
from astrbot.core.platform.sources.wecom_ai_bot.WXBizJsonMsgCrypt import (
    WXBizJsonMsgCrypt,
)
from Crypto.Cipher import AES
import requests

app = FastAPI()

# 常量定义
CACHE_DIR = "/tmp/llm_demo_cache"
MAX_STEPS = 10

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _generate_random_string(length):
    letters = string.ascii_letters + string.digits
    return "".join(random.choice(letters) for _ in range(length))


def _process_encrypted_image(image_url, aes_key_base64):
    """
    下载并解密加密图片

    参数:
        image_url: 加密图片的URL
        aes_key_base64: Base64编码的AES密钥(与回调加解密相同)

    返回:
        tuple: (status: bool, data: bytes/str)
               status为True时data是解密后的图片数据，
               status为False时data是错误信息
    """
    try:
        # 1. 下载加密图片
        logger.info("开始下载加密图片: %s", image_url)
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()
        encrypted_data = response.content
        logger.info("图片下载成功，大小: %d 字节", len(encrypted_data))

        # 2. 准备AES密钥和IV
        if not aes_key_base64:
            raise ValueError("AES密钥不能为空")

        # Base64解码密钥 (自动处理填充)
        aes_key = base64.b64decode(aes_key_base64 + "=" * (-len(aes_key_base64) % 4))
        if len(aes_key) != 32:
            raise ValueError("无效的AES密钥长度: 应为32字节")

        iv = aes_key[:16]  # 初始向量为密钥前16字节

        # 3. 解密图片数据
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted_data = cipher.decrypt(encrypted_data)

        # 4. 去除PKCS#7填充 (Python 3兼容写法)
        pad_len = decrypted_data[-1]  # 直接获取最后一个字节的整数值
        if pad_len > 32:  # AES-256块大小为32字节
            raise ValueError("无效的填充长度 (大于32字节)")

        decrypted_data = decrypted_data[:-pad_len]
        logger.info("图片解密成功，解密后大小: %d 字节", len(decrypted_data))

        return True, decrypted_data

    except requests.exceptions.RequestException as e:
        error_msg = f"图片下载失败 : {str(e)}"
        logger.error(error_msg)
        return False, error_msg

    except ValueError as e:
        error_msg = f"参数错误 : {str(e)}"
        logger.error(error_msg)
        return False, error_msg

    except Exception as e:
        error_msg = f"图片处理异常 : {str(e)}"
        logger.error(error_msg)
        return False, error_msg


def MakeTextStream(stream_id, content, finish):
    plain = {
        "msgtype": "stream",
        "stream": {"id": stream_id, "finish": finish, "content": content},
    }
    return json.dumps(plain, ensure_ascii=False)


def MakeImageStream(stream_id, image_data, finish):
    image_md5 = hashlib.md5(image_data).hexdigest()
    image_base64 = base64.b64encode(image_data).decode("utf-8")

    plain = {
        "msgtype": "stream",
        "stream": {
            "id": stream_id,
            "finish": finish,
            "msg_item": [
                {
                    "msgtype": "image",
                    "image": {"base64": image_base64, "md5": image_md5},
                }
            ],
        },
    }
    return json.dumps(plain)


def EncryptMessage(receiveid, nonce, timestamp, stream):
    logger.info(
        "开始加密消息，receiveid=%s, nonce=%s, timestamp=%s",
        receiveid,
        nonce,
        timestamp,
    )
    logger.debug("发送流消息: %s", stream)

    wxcpt = WXBizJsonMsgCrypt(
        os.getenv("Token", ""), os.getenv("EncodingAESKey", ""), receiveid
    )
    ret, resp = wxcpt.EncryptMsg(stream, nonce, timestamp)
    if ret != 0:
        logger.error("加密失败，错误码: %d", ret)
        return

    stream_id = json.loads(stream)["stream"]["id"]
    finish = json.loads(stream)["stream"]["finish"]
    logger.info(
        "回调处理完成, 返回加密的流消息, stream_id=%s, finish=%s", stream_id, finish
    )
    logger.debug("加密后的消息: %s", resp)

    return resp


# TODO 这里模拟一个大模型的行为
class LLMDemo:
    def __init__(self):
        self.cache_dir = CACHE_DIR
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def invoke(self, question):
        stream_id = _generate_random_string(10)  # 生成一个随机字符串作为任务ID
        # 创建任务缓存文件
        cache_file = os.path.join(self.cache_dir, "%s.json" % stream_id)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "question": question,
                    "created_time": time.time(),
                    "current_step": 0,
                    "max_steps": MAX_STEPS,
                },
                f,
            )
        return stream_id

    def get_answer(self, stream_id):
        cache_file = os.path.join(self.cache_dir, "%s.json" % stream_id)
        if not os.path.exists(cache_file):
            return "任务不存在或已过期"

        with open(cache_file, "r", encoding="utf-8") as f:
            task_data = json.load(f)

        # 更新缓存
        current_step = task_data["current_step"] + 1
        task_data["current_step"] = current_step
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(task_data, f)

        response = "收到问题：%s\n" % task_data["question"]
        for i in range(current_step):
            response += "处理步骤 %d: 已完成\n" % (i)

        return response

    def is_task_finish(self, stream_id):
        cache_file = os.path.join(self.cache_dir, "%s.json" % stream_id)
        if not os.path.exists(cache_file):
            return True

        with open(cache_file, "r", encoding="utf-8") as f:
            task_data = json.load(f)

        return task_data["current_step"] >= task_data["max_steps"]


@app.get("/ai-bot/callback/demo/{botid}")
async def verify_url(
    request: Request,
    botid: str,
    msg_signature: str,
    timestamp: str,
    nonce: str,
    echostr: str,
):
    # 企业创建的自能机器人的 VerifyUrl 请求, receiveid 是空串
    receiveid = ""
    wxcpt = WXBizJsonMsgCrypt(
        os.getenv("Token", ""), os.getenv("EncodingAESKey", ""), receiveid
    )

    ret, echostr = wxcpt.VerifyURL(msg_signature, timestamp, nonce, echostr)

    if ret != 0:
        echostr = "verify fail"

    return Response(content=echostr, media_type="text/plain")


@app.post("/ai-bot/callback/demo/{botid}")
async def handle_message(
    request: Request,
    botid: str,
    msg_signature: str = None,
    timestamp: str = None,
    nonce: str = None,
):
    query_params = dict(request.query_params)
    if not all([msg_signature, timestamp, nonce]):
        raise HTTPException(status_code=400, detail="缺少必要参数")
    logger.info(
        "收到消息，botid=%s, msg_signature=%s, timestamp=%s, nonce=%s",
        botid,
        msg_signature,
        timestamp,
        nonce,
    )

    post_data = await request.body()

    # 智能机器人的 receiveid 是空串
    receiveid = ""
    wxcpt = WXBizJsonMsgCrypt(
        os.getenv("Token", ""), os.getenv("EncodingAESKey", ""), receiveid
    )

    ret, msg = wxcpt.DecryptMsg(post_data, msg_signature, timestamp, nonce)

    if ret != 0:
        raise HTTPException(status_code=400, detail="解密失败")

    data = json.loads(msg)
    logger.debug("Decrypted data: %s", data)
    if "msgtype" not in data:
        logger.info("不认识的事件: %s", data)
        return Response(content="success", media_type="text/plain")

    msgtype = data["msgtype"]
    if msgtype == "text":
        content = data["text"]["content"]

        # 询问大模型产生回复
        llm = LLMDemo()
        stream_id = llm.invoke(content)
        answer = llm.get_answer(stream_id)
        finish = llm.is_task_finish(stream_id)

        stream = MakeTextStream(stream_id, answer, finish)
        resp = EncryptMessage(receiveid, nonce, timestamp, stream)
        return Response(content=resp, media_type="text/plain")
    elif msgtype == "stream":  # case stream
        # 询问大模型最新的回复
        stream_id = data["stream"]["id"]
        llm = LLMDemo()
        answer = llm.get_answer(stream_id)
        finish = llm.is_task_finish(stream_id)

        stream = MakeTextStream(stream_id, answer, finish)
        resp = EncryptMessage(receiveid, nonce, timestamp, stream)
        return Response(content=resp, media_type="text/plain")
    elif msgtype == "image":
        # 从环境变量获取AES密钥
        aes_key = os.getenv("EncodingAESKey", "")

        # 调用图片处理函数
        success, result = _process_encrypted_image(data["image"]["url"], aes_key)
        if not success:
            logger.error("图片处理失败: %s", result)
            return

        # 这里简单处理直接原图回复
        decrypted_data = result
        stream_id = _generate_random_string(10)
        finish = True

        stream = MakeImageStream(stream_id, decrypted_data, finish)
        resp = EncryptMessage(receiveid, nonce, timestamp, stream)
        return Response(content=resp, media_type="text/plain")
    elif msgtype == "mixed":
        # TODO 处理图文混排消息
        logger.warning("需要支持mixed消息类型")
    elif msgtype == "event":
        # TODO 一些事件的处理
        logger.warning("需要支持event消息类型: %s", data)
        return
    else:
        logger.warning("不支持的消息类型: %s", msgtype)
        return


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=80)
