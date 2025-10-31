import json
import logging
import re
from typing import Any

from openai.types.chat.chat_completion import ChatCompletion

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star

try:
    # 谨慎引入，避免在未安装 google-genai 的环境下报错
    from google.genai.types import GenerateContentResponse
except Exception:  # pragma: no cover - 兼容无此依赖的运行环境
    GenerateContentResponse = None  # type: ignore


class R1Filter(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.on_llm_response()
    async def resp(self, event: AstrMessageEvent, response: LLMResponse):
        cfg = self.context.get_config(umo=event.unified_msg_origin).get(
            "provider_settings",
            {},
        )
        show_reasoning = cfg.get("display_reasoning_text", False)

        # --- Gemini: 过滤/展示 thought:true 片段 ---
        # Gemini 可能在 parts 中注入 {"thought": true, "text": "..."}
        # 官方 SDK 默认不会返回此字段。
        if GenerateContentResponse is not None and isinstance(
            response.raw_completion,
            GenerateContentResponse,
        ):
            thought_text, answer_text = self._extract_gemini_texts(
                response.raw_completion,
            )

            if thought_text or answer_text:
                # 有明确的思考/正文分离信号，则按配置处理
                if show_reasoning:
                    merged = (
                        (f"🤔思考：{thought_text}\n\n" if thought_text else "")
                        + (answer_text or "")
                    ).strip()
                    if merged:
                        response.completion_text = merged
                        return
                # 默认隐藏思考内容，仅保留正文
                elif answer_text:
                    response.completion_text = answer_text
                    return

        # --- 非 Gemini 或无明确 thought:true 情况 ---
        if show_reasoning:
            # 显示推理内容的处理逻辑
            if (
                response
                and response.raw_completion
                and isinstance(response.raw_completion, ChatCompletion)
                and len(response.raw_completion.choices) > 0
                and response.raw_completion.choices[0].message
            ):
                message = response.raw_completion.choices[0].message
                reasoning_content = ""  # 初始化 reasoning_content

                # 检查 Groq deepseek-r1-distill-llama-70b 模型的 'reasoning' 属性
                if hasattr(message, "reasoning") and message.reasoning:
                    reasoning_content = message.reasoning
                # 检查 DeepSeek deepseek-reasoner 模型的 'reasoning_content'
                elif (
                    hasattr(message, "reasoning_content") and message.reasoning_content
                ):
                    reasoning_content = message.reasoning_content

                if reasoning_content:
                    response.completion_text = (
                        f"🤔思考：{reasoning_content}\n\n{message.content}"
                    )
                else:
                    response.completion_text = message.content
        else:
            # 过滤推理标签的处理逻辑
            completion_text = response.completion_text

            # 检查并移除 <think> 标签
            if r"<think>" in completion_text or r"</think>" in completion_text:
                # 移除配对的标签及其内容
                completion_text = re.sub(
                    r"<think>.*?</think>",
                    "",
                    completion_text,
                    flags=re.DOTALL,
                ).strip()

                # 移除可能残留的单个标签
                completion_text = (
                    completion_text.replace(r"<think>", "")
                    .replace(r"</think>", "")
                    .strip()
                )

            response.completion_text = completion_text

    # ------------------------
    # helpers
    # ------------------------
    def _get_part_dict(self, p: Any) -> dict:
        """优先使用 SDK 标准序列化方法获取字典，失败则逐级回退。

        顺序: model_dump → model_dump_json → json → to_dict → dict → __dict__。
        """
        for getter in ("model_dump", "model_dump_json", "json", "to_dict", "dict"):
            fn = getattr(p, getter, None)
            if callable(fn):
                try:
                    result = fn()
                    if isinstance(result, (str, bytes)):
                        try:
                            if isinstance(result, bytes):
                                result = result.decode("utf-8", "ignore")
                            return json.loads(result) or {}
                        except json.JSONDecodeError:
                            continue
                    if isinstance(result, dict):
                        return result
                except (AttributeError, TypeError):
                    continue
                except Exception as e:
                    logging.exception(
                        f"Unexpected error when calling {getter} on {type(p).__name__}: {e}",
                    )
                    continue
        try:
            d = getattr(p, "__dict__", None)
            if isinstance(d, dict):
                return d
        except (AttributeError, TypeError):
            pass
        except Exception as e:
            logging.exception(
                f"Unexpected error when accessing __dict__ on {type(p).__name__}: {e}",
            )
        return {}

    def _is_thought_part(self, p: Any) -> bool:
        """判断是否为思考片段。

        规则:
        1) 直接 thought 属性
        2) 字典字段 thought 或 metadata.thought
        3) data/raw/extra/_raw 中嵌入的 JSON 串包含 thought: true
        """
        try:
            if getattr(p, "thought", False):
                return True
        except Exception:
            # best-effort
            pass

        d = self._get_part_dict(p)
        if d.get("thought") is True:
            return True
        meta = d.get("metadata")
        if isinstance(meta, dict) and meta.get("thought") is True:
            return True
        for k in ("data", "raw", "extra", "_raw"):
            v = d.get(k)
            if isinstance(v, (str, bytes)):
                try:
                    if isinstance(v, bytes):
                        v = v.decode("utf-8", "ignore")
                    parsed = json.loads(v)
                    if isinstance(parsed, dict) and parsed.get("thought") is True:
                        return True
                except json.JSONDecodeError:
                    continue
        return False

    def _extract_gemini_texts(self, resp: Any) -> tuple[str, str]:
        """从 GenerateContentResponse 中提取 (思考文本, 正文文本)。"""
        try:
            cand0 = next(iter(getattr(resp, "candidates", []) or []), None)
            if not cand0:
                return "", ""
            content = getattr(cand0, "content", None)
            parts = getattr(content, "parts", None) or []
        except (AttributeError, TypeError, ValueError):
            return "", ""

        thought_buf: list[str] = []
        answer_buf: list[str] = []
        for p in parts:
            txt = getattr(p, "text", None)
            if txt is None:
                continue
            txt_str = str(txt).strip()
            if not txt_str:
                continue
            if self._is_thought_part(p):
                thought_buf.append(txt_str)
            else:
                answer_buf.append(txt_str)

        return "\n".join(thought_buf).strip(), "\n".join(answer_buf).strip()
