"""
[PATCH: 2026-06-03] 升级: V1 API → V3 HTTP Chunked 单向流式 API
============================================================
变更内容:
  1. 鉴权方式: 旧版 (appid + token + cluster) → 新版 (X-Api-Key header)
  2. 接口地址: POST api/v1/tts → POST api/v3/tts/unidirectional (chunked streaming)
  3. 新增模型选择: X-Api-Resource-Id header 可选 seed-tts-2.0 / seed-icl-2.0 等
  4. 新增音频参数: speech_rate(语速), loudness_rate(音量), pitch(音调), emotion(情感)
  5. 响应解析: 单次 JSON → NDJSON 流式解析 base64 音频

参考文档:
  - V3 HTTP Chunked API: https://www.volcengine.com/docs/6561/1598757
  - 音色列表:          https://www.volcengine.com/docs/6561/1257544
  - API Key 管理:      https://www.volcengine.com/docs/6561/2119699

易错点排查:
  - 音色需与 resource_id 匹配: _uranus_ 后缀音色 → seed-tts-2.0
  - bit_rate 不传则默认 8k, MP3 音质会很差, 建议显式设为 128000
  - pitch 通过 additions.post_process.pitch 传入 (JSON string)
"""

import asyncio
import base64
import json
import os
import re
import traceback
import uuid

import aiohttp

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

from ..entities import ProviderType
from ..provider import TTSProvider
from ..register import register_provider_adapter


# ============================================================
# 可用的 resource_id 及其对应模型 (供 WebUI 配置参考)
# ============================================================
# seed-tts-2.0          → 豆包语音合成模型 2.0 (推荐, 音色带 _uranus_ 后缀)
# seed-tts-1.0          → 豆包语音合成模型 1.0
# seed-tts-1.0-concurr  → 豆包语音合成模型 1.0 并发版
# seed-icl-2.0          → 声音复刻 2.0
# seed-icl-1.0          → 声音复刻 1.0
# seed-icl-1.0-concurr  → 声音复刻 1.0 并发版


@register_provider_adapter(
    "volcengine_tts",
    "火山引擎 TTS (V3)",
    provider_type=ProviderType.TEXT_TO_SPEECH,
)
class ProviderVolcengineTTS(TTSProvider):
    """
    火山引擎 TTS Provider — V3 HTTP Chunked 单向流式 API 实现

    用法:
      在 AstrBot WebUI → 配置 → TTS Provider 中选择 "火山引擎 TTS (V3)"
      填入 API Key (火山引擎新版控制台获取) 和音色 speaker 即可
    """

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        super().__init__(provider_config, provider_settings)

        # === [V3 新] 鉴权: X-Api-Key ===
        # 从火山引擎新版控制台 (console.volcengine.com/speech/new) 获取
        # 兼容旧配置: 旧版可能把 token 存在 api_key 字段, 升级后需替换为新的 API Key
        self.api_key = provider_config.get("api_key", "")

        # === [V3 新] 模型/资源选择: X-Api-Resource-Id ===
        # 决定了模型版本和计费方式, 必须与音色匹配
        # 例如 zh_female_meilinvyou_uranus_bigtts 需要 seed-tts-2.0
        self.resource_id = provider_config.get("resource_id", "seed-tts-2.0")

        # === 音色 (兼容旧字段 voice_type) ===
        # speaker: 发音人标识, 见 https://www.volcengine.com/docs/6561/1257544
        self.speaker = provider_config.get("speaker") or provider_config.get("voice_type", "")

        # === [V3 新] 音频格式 ===
        # format: mp3 / ogg_opus / pcm (pcm 无文件头, 流式场景推荐)
        self.format = provider_config.get("format", "mp3")
        # sample_rate: 8000 / 16000 / 22050 / 24000 / 32000 / 44100 / 48000
        self.sample_rate = provider_config.get("sample_rate", 24000)
        # bit_rate: MP3 格式强烈建议显式设置 (如 128000), 不传则默认为 8k 音质很差
        self.bit_rate = provider_config.get("bit_rate", 128000)

        # === [V3 新] 语调/语速 ===
        # speech_rate: -50~100, 默认 0; 100=2倍速, -50=0.5倍速
        self.speech_rate = provider_config.get("speech_rate", 0)

        # === [V3 新] 音量 ===
        # loudness_rate: -50~100, 默认 0; 100=2倍音量, -50=0.5倍音量
        self.loudness_rate = provider_config.get("loudness_rate", 0)

        # === [V3 新] 情感 ===
        # emotion: 仅部分音色支持, 见音色列表中的"支持的情感"列
        # 中文可选: happy, sad, angry, surprised, fear, hate, excited, coldness,
        #           neutral, depressed, lovey-dovey(撒娇), shy, comfort, tension,
        #           tender, storytelling, radio, magnetic, advertising, vocal-fry,
        #           ASMR, news, entertainment, dialect
        self.emotion = provider_config.get("emotion", "")
        # emotion_scale: 情感强度 1~5, 默认 4 (仅当 emotion 设置后生效)
        self.emotion_scale = provider_config.get("emotion_scale", 4)

        # === [V3 新] 音调 (通过 additions.post_process.pitch) ===
        # pitch: -12~12, 默认 0; 正值=升调, 负值=降调
        self.pitch = provider_config.get("pitch", 0)

        # === [V3 新] 模型子类型 (仅声音复刻 2.0 / seed-icl-2.0 生效) ===
        # seed-tts-2.0-standard:  标准版, 延时更优
        # seed-tts-2.0-expressive: 表现力增强版, 效果更好但可能不稳定
        self.model = provider_config.get("model", "")

        # === 超时时间 (秒) ===
        self.timeout = provider_config.get("timeout", 30)

        # === API 地址 (可自定义, 如代理) ===
        self.api_base = provider_config.get(
            "api_base",
            "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        )

    def _build_payload(self, text: str) -> dict:
        """
        [V3] 构建请求体

        请求格式参考: https://www.volcengine.com/docs/6561/1598757#_2-2-请求body
        """
        # --- audio_params ---
        audio_params: dict = {
            "format": self.format,
            "sample_rate": self.sample_rate,
            "speech_rate": self.speech_rate,
            "loudness_rate": self.loudness_rate,
        }

        if self.bit_rate is not None:
            audio_params["bit_rate"] = self.bit_rate

        if self.emotion:
            audio_params["emotion"] = self.emotion
            audio_params["emotion_scale"] = self.emotion_scale

        # --- additions (JSON string) ---
        additions: dict = {}
        if self.pitch != 0:
            additions["post_process"] = {"pitch": self.pitch}

        # --- 主请求体 ---
        payload: dict = {
            "user": {"uid": str(uuid.uuid4())[:8]},
            "namespace": "BidirectionalTTS",
            "req_params": {
                "text": text,
                "speaker": self.speaker,
                "audio_params": audio_params,
            },
        }

        if self.model:
            payload["req_params"]["model"] = self.model

        if additions:
            payload["req_params"]["additions"] = json.dumps(additions, ensure_ascii=False)

        return payload

    async def get_audio(self, text: str) -> str:
        """
        [V3] 调用 HTTP Chunked 单向流式 API 合成语音

        返回: 生成的音频文件绝对路径

        异常处理:
          - HTTP 非 200: 抛出包含状态码和响应体的异常
          - API 返回错误: 抛出包含 code/message 的异常
          - 无音频数据: 抛出提示异常
        """
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self.resource_id,
        }

        payload = self._build_payload(text)

        logger.debug(f"[VolcengineTTS V3] text_len={len(text)}, text_head={repr(text[:60])}")
        logger.debug(f"[VolcengineTTS V3] URL={self.api_base}")
        logger.debug(f"[VolcengineTTS V3] resource_id={self.resource_id}, speaker={self.speaker}")
        logger.debug(f"[VolcengineTTS V3] speech_rate={self.speech_rate}, loudness_rate={self.loudness_rate}, pitch={self.pitch}")
        logger.debug(f"[VolcengineTTS V3] model={self.model or '(default)'}")

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    self.api_base,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response,
            ):
                # --- 记录响应用于排错 ---
                logid = response.headers.get("X-Tt-Logid", "N/A")
                logger.debug(f"[VolcengineTTS V3] status={response.status}, logid={logid}")

                if response.status != 200:
                    error_body = await response.text()
                    logger.error(f"[VolcengineTTS V3] HTTP {response.status}: {error_body[:500]}")
                    raise Exception(
                        f"火山引擎 TTS 请求失败 (HTTP {response.status}, logid={logid}): {error_body[:300]}"
                    )

                # --- 读取 chunked 响应 (NDJSON 格式, 每行一个 JSON 对象) ---
                # 响应示例:
                #   {"event":"TTSSentenceStart", ...}
                #   {"audio":{"data":"//uQx..."}, "event":"TTSSentenceEnd", ...}
                #   {"event":"TTSResponse", "usage":{...}}
                raw_body = b""
                async for chunk in response.content.iter_any():
                    if chunk:
                        raw_body += chunk

                if not raw_body:
                    raise Exception(
                        f"火山引擎 TTS 返回空响应 (logid={logid})，请检查 API Key 和 resource_id 是否正确"
                    )

                # PATCH: 2026-06-03 - V3 unidirectional API returns either single JSON or NDJSON streaming.
                # Shorter texts → single JSON {"code":0,"data":"<base64>"}
                # Longer texts → NDJSON stream with multiple {"code":...,"data":"<base64>",...} lines
                audio_chunks: list[bytes] = []
                last_event = ""
                raw_text = raw_body.decode("utf-8", errors="replace")

                # --- Approach 1: NDJSON (streaming format — primary for unidirectional API) ---
                lines = [l for l in raw_text.strip().split("\n") if l.strip()]
                if len(lines) > 1:
                    logger.debug(f"[VolcengineTTS V3] NDJSON mode: {len(lines)} lines, {len(raw_body)} bytes")
                    for line in lines:
                        line = line.strip()
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if "error" in data:
                            raise Exception(
                                f"火山引擎 TTS API 错误 (logid={logid}): {json.dumps(data['error'], ensure_ascii=False)}"
                            )
                        if "code" in data:
                            code = data.get("code", 0)
                            if code not in (0, 20000000):
                                raise Exception(
                                    f"火山引擎 TTS API 错误 (logid={logid}): "
                                    f"code={code}, message={data.get('message', 'unknown')}"
                                )

                        event = data.get("event", "")
                        if event:
                            last_event = event

                        # NDJSON: each line may have either "data" at top level or "audio.data" nested
                        if "data" in data and isinstance(data["data"], str):
                            b64_str = re.sub(r'\s+', '', data["data"])
                            try:
                                audio_chunks.append(base64.b64decode(b64_str))
                            except Exception:
                                pass
                        elif "audio" in data and "data" in data["audio"]:
                            audio_chunks.append(base64.b64decode(data["audio"]["data"]))

                # --- Approach 2: single JSON (fallback for short texts) ---
                if not audio_chunks:
                    logger.debug(f"[VolcengineTTS V3] single JSON mode, {len(raw_body)} bytes")
                    obj = json.loads(raw_text)
                    if "data" in obj and obj["data"] and isinstance(obj["data"], str):
                        b64_str = re.sub(r'\s+', '', obj["data"])
                        audio_chunks.append(base64.b64decode(b64_str))

                if not audio_chunks:
                    raise Exception(
                        f"火山引擎 TTS 未返回音频数据 (logid={logid}, last_event={last_event})。"
                        f"可能原因: 1) speaker 与 resource_id 不匹配 "
                        f"2) API Key 对应的服务未开通 "
                        f"3) 文本内容触发了安全过滤"
                    )

                # --- 拼接音频片段并写入文件 ---
                full_audio = b"".join(audio_chunks)

                temp_dir = get_astrbot_temp_path()
                os.makedirs(temp_dir, exist_ok=True)
                file_path = os.path.join(temp_dir, f"volcengine_tts_{uuid.uuid4().hex[:12]}.{self.format}")

                # 异步写入文件 (避免阻塞事件循环)
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: open(file_path, "wb").write(full_audio))

                logger.info(
                    f"[VolcengineTTS V3] 合成完成: {file_path} "
                    f"({len(full_audio)} bytes, {len(audio_chunks)} chunks, logid={logid})"
                )
                return file_path

        except aiohttp.ClientError as e:
            logger.error(f"[VolcengineTTS V3] 网络异常: {traceback.format_exc()}")
            raise Exception(f"火山引擎 TTS 网络请求失败: {e!s}")
        except Exception:
            # 重新抛出已包含详细信息的异常
            raise
