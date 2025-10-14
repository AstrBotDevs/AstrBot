#!/usr/bin/env python
# -*- encoding:utf-8 -*-

"""对企业微信发送给企业后台的消息加解密示例代码.
@copyright: Copyright (c) 1998-2020 Tencent Inc.

"""
# ------------------------------------------------------------------------

import logging
import base64
import random
import hashlib
import time
import struct
from Crypto.Cipher import AES
import socket
import json

from . import ierror

"""
关于Crypto.Cipher模块，ImportError: No module named 'Crypto'解决方案
请到官方网站 https://www.dlitz.net/software/pycrypto/ 下载pycrypto。
下载后，按照README中的“Installation”小节的提示进行pycrypto安装。
"""


class FormatException(Exception):
    pass


def throw_exception(message, exception_class=FormatException):
    """my define raise exception function"""
    raise exception_class(message)


class SHA1:
    """计算企业微信的消息签名接口"""

    def getSHA1(self, token, timestamp, nonce, encrypt):
        """用SHA1算法生成安全签名
        @param token:  票据
        @param timestamp: 时间戳
        @param encrypt: 密文
        @param nonce: 随机字符串
        @return: 安全签名
        """
        try:
            # 确保所有输入都是字符串类型
            if isinstance(encrypt, bytes):
                encrypt = encrypt.decode("utf-8")

            sortlist = [str(token), str(timestamp), str(nonce), str(encrypt)]
            sortlist.sort()
            sha = hashlib.sha1()
            sha.update("".join(sortlist).encode("utf-8"))
            return ierror.WXBizMsgCrypt_OK, sha.hexdigest()

        except Exception as e:
            print(e)
            return ierror.WXBizMsgCrypt_ComputeSignature_Error, None


class JsonParse:
    """提供提取消息格式中的密文及生成回复消息格式的接口"""

    # json消息模板
    AES_TEXT_RESPONSE_TEMPLATE = """{
        "encrypt": "%(msg_encrypt)s",
        "msgsignature": "%(msg_signaturet)s",
        "timestamp": "%(timestamp)s",
        "nonce": "%(nonce)s"
    }"""

    def extract(self, jsontext):
        """提取出json数据包中的加密消息
        @param jsontext: 待提取的json字符串
        @return: 提取出的加密消息字符串
        """
        try:
            json_dict = json.loads(jsontext)
            return ierror.WXBizMsgCrypt_OK, json_dict["encrypt"]
        except Exception as e:
            print(e)
            return ierror.WXBizMsgCrypt_ParseJson_Error, None

    def generate(self, encrypt, signature, timestamp, nonce):
        """生成json消息
        @param encrypt: 加密后的消息密文
        @param signature: 安全签名
        @param timestamp: 时间戳
        @param nonce: 随机字符串
        @return: 生成的json字符串
        """
        resp_dict = {
            "msg_encrypt": encrypt,
            "msg_signaturet": signature,
            "timestamp": timestamp,
            "nonce": nonce,
        }
        resp_json = self.AES_TEXT_RESPONSE_TEMPLATE % resp_dict
        return resp_json


class PKCS7Encoder:
    """提供基于PKCS7算法的加解密接口"""

    block_size = 32

    def encode(self, text):
        """对需要加密的明文进行填充补位
        @param text: 需要进行填充补位操作的明文(bytes类型)
        @return: 补齐明文字符串(bytes类型)
        """
        text_length = len(text)
        # 计算需要填充的位数
        amount_to_pad = self.block_size - (text_length % self.block_size)
        if amount_to_pad == 0:
            amount_to_pad = self.block_size
        # 获得补位所用的字符
        pad = bytes([amount_to_pad])
        # 确保text是bytes类型
        if isinstance(text, str):
            text = text.encode("utf-8")
        return text + pad * amount_to_pad

    def decode(self, decrypted):
        """删除解密后明文的补位字符
        @param decrypted: 解密后的明文
        @return: 删除补位字符后的明文
        """
        pad = ord(decrypted[-1])
        if pad < 1 or pad > 32:
            pad = 0
        return decrypted[:-pad]


class Prpcrypt(object):
    """提供接收和推送给企业微信消息的加解密接口"""

    def __init__(self, key):
        # self.key = base64.b64decode(key+"=")
        self.key = key
        # 设置加解密模式为AES的CBC模式
        self.mode = AES.MODE_CBC

    def encrypt(self, text, receiveid):
        """对明文进行加密
        @param text: 需要加密的明文
        @return: 加密得到的字符串
        """
        # 16位随机字符串添加到明文开头
        text = text.encode()
        text = (
            self.get_random_str()
            + struct.pack("I", socket.htonl(len(text)))
            + text
            + receiveid.encode()
        )

        # 使用自定义的填充方式对明文进行补位填充
        pkcs7 = PKCS7Encoder()
        text = pkcs7.encode(text)
        # 加密
        cryptor = AES.new(self.key, self.mode, self.key[:16])  # type: ignore
        try:
            ciphertext = cryptor.encrypt(text)
            # 使用BASE64对加密后的字符串进行编码
            return ierror.WXBizMsgCrypt_OK, base64.b64encode(ciphertext)
        except Exception as e:
            logger = logging.getLogger("astrbot")
            logger.error(e)
            return ierror.WXBizMsgCrypt_EncryptAES_Error, None

    def decrypt(self, text, receiveid):
        """对解密后的明文进行补位删除
        @param text: 密文
        @return: 删除填充补位后的明文
        """
        try:
            cryptor = AES.new(self.key, self.mode, self.key[:16])  # type: ignore
            # 使用BASE64对密文进行解码，然后AES-CBC解密
            plain_text = cryptor.decrypt(base64.b64decode(text))
        except Exception as e:
            print(e)
            return ierror.WXBizMsgCrypt_DecryptAES_Error, None
        try:
            pad = plain_text[-1]
            # 去掉补位字符串
            # pkcs7 = PKCS7Encoder()
            # plain_text = pkcs7.encode(plain_text)
            # 去除16位随机字符串
            content = plain_text[16:-pad]
            json_len = socket.ntohl(struct.unpack("I", content[:4])[0])
            json_content = content[4 : json_len + 4].decode("utf-8")
            from_receiveid = content[json_len + 4 :].decode("utf-8")
        except Exception as e:
            print(e)
            return ierror.WXBizMsgCrypt_IllegalBuffer, None
        if from_receiveid != receiveid:
            print("receiveid not match", receiveid, from_receiveid)
            return ierror.WXBizMsgCrypt_ValidateCorpid_Error, None
        return 0, json_content

    def get_random_str(self):
        """随机生成16位字符串
        @return: 16位字符串
        """
        return str(random.randint(1000000000000000, 9999999999999999)).encode()


class WXBizJsonMsgCrypt(object):
    # 构造函数
    def __init__(self, sToken, sEncodingAESKey, sReceiveId):
        try:
            self.key = base64.b64decode(sEncodingAESKey + "=")
            assert len(self.key) == 32
        except Exception as e:
            throw_exception(f"[error]: EncodingAESKey invalid: {e}", FormatException)
            # return ierror.WXBizMsgCrypt_IllegalAesKey,None
        self.m_sToken = sToken
        self.m_sReceiveId = sReceiveId

    # 验证URL
    # @param sMsgSignature: 签名串，对应URL参数的msg_signature
    # @param sTimeStamp: 时间戳，对应URL参数的timestamp
    # @param sNonce: 随机串，对应URL参数的nonce
    # @param sEchoStr: 随机串，对应URL参数的echostr
    # @param sReplyEchoStr: 解密之后的echostr，当return返回0时有效
    # @return：成功0，失败返回对应的错误码

    def VerifyURL(self, sMsgSignature, sTimeStamp, sNonce, sEchoStr):
        sha1 = SHA1()
        ret, signature = sha1.getSHA1(self.m_sToken, sTimeStamp, sNonce, sEchoStr)
        if ret != 0:
            return ret, None
        if not signature == sMsgSignature:
            return ierror.WXBizMsgCrypt_ValidateSignature_Error, None
        pc = Prpcrypt(self.key)
        ret, sReplyEchoStr = pc.decrypt(sEchoStr, self.m_sReceiveId)
        return ret, sReplyEchoStr

    def EncryptMsg(self, sReplyMsg, sNonce, timestamp=None):
        # 将企业回复用户的消息加密打包
        # @param sReplyMsg: 企业号待回复用户的消息，json格式的字符串
        # @param sTimeStamp: 时间戳，可以自己生成，也可以用URL参数的timestamp,如为None则自动用当前时间
        # @param sNonce: 随机串，可以自己生成，也可以用URL参数的nonce
        # sEncryptMsg: 加密后的可以直接回复用户的密文，包括msg_signature, timestamp, nonce, encrypt的json格式的字符串,
        # return：成功0，sEncryptMsg,失败返回对应的错误码None
        pc = Prpcrypt(self.key)
        ret, encrypt = pc.encrypt(sReplyMsg, self.m_sReceiveId)
        encrypt = encrypt.decode("utf-8")  # type: ignore
        if ret != 0:
            return ret, None
        if timestamp is None:
            timestamp = str(int(time.time()))
        # 生成安全签名
        sha1 = SHA1()
        ret, signature = sha1.getSHA1(self.m_sToken, timestamp, sNonce, encrypt)
        if ret != 0:
            return ret, None
        jsonParse = JsonParse()
        return ret, jsonParse.generate(encrypt, signature, timestamp, sNonce)

    def DecryptMsg(self, sPostData, sMsgSignature, sTimeStamp, sNonce):
        # 检验消息的真实性，并且获取解密后的明文
        # @param sMsgSignature: 签名串，对应URL参数的msg_signature
        # @param sTimeStamp: 时间戳，对应URL参数的timestamp
        # @param sNonce: 随机串，对应URL参数的nonce
        # @param sPostData: 密文，对应POST请求的数据
        #  json_content: 解密后的原文，当return返回0时有效
        # @return: 成功0，失败返回对应的错误码
        # 验证安全签名
        jsonParse = JsonParse()
        ret, encrypt = jsonParse.extract(sPostData)
        if ret != 0:
            return ret, None
        sha1 = SHA1()
        ret, signature = sha1.getSHA1(self.m_sToken, sTimeStamp, sNonce, encrypt)
        if ret != 0:
            return ret, None
        if not signature == sMsgSignature:
            print("signature not match")
            print(signature)
            return ierror.WXBizMsgCrypt_ValidateSignature_Error, None
        pc = Prpcrypt(self.key)
        ret, json_content = pc.decrypt(encrypt, self.m_sReceiveId)
        return ret, json_content
