"""Author: diudiu62
Date: 2025-02-24 18:04:18
LastEditTime: 2025-02-25 14:06:30
"""

import asyncio
import os
import re
from typing import cast

from funasr_onnx import SenseVoiceSmall
from funasr_onnx.utils.postprocess_utils import rich_transcription_postprocess

from astrbot.core import logger
from astrbot.core.utils.media_utils import MediaResolver

from ..entities import ProviderType
from ..provider import STTProvider
from ..register import register_provider_adapter


@register_provider_adapter(
    "sensevoice_stt_selfhost",
    "SenseVoice 自托管语音识别 模型部署",
    provider_type=ProviderType.SPEECH_TO_TEXT,
    default_config_tmpl={
        "id": "sensevoice",
        "stt_model": "iic/SenseVoiceSmall",
        "is_emotion": False,
    },
)
class ProviderSenseVoiceSTTSelfHost(STTProvider):
    def __init__(
        self,
        provider_config: dict,
        provider_settings: dict,
    ) -> None:
        super().__init__(provider_config, provider_settings)
        self.set_model(provider_config["stt_model"])
        self.model = None
        self.is_emotion = provider_config.get("is_emotion", False)

    async def initialize(self) -> None:
        logger.info("下载或者加载 SenseVoice 模型中，这可能需要一些时间 ...")

        def _load_model():
            try:
                return SenseVoiceSmall(self.model_name, quantize=True, batch_size=16)
            except Exception as e:
                err_str = str(e)
                if "Type parameter (T) of Optype (Less) bound to different types" in err_str:
                    logger.info("检测到 ONNX 导出类型不匹配，正在修复导出的模型文件 ...")
                    self._fix_onnx_less_type_mismatch()
                    # 重试加载，此时 model_quant.onnx 已被修复
                    return SenseVoiceSmall(
                        self.model_name, quantize=True, batch_size=16
                    )
                raise

        self.model = await asyncio.get_running_loop().run_in_executor(
            None, _load_model,
        )

        logger.info("SenseVoice 模型加载完成。")

    @staticmethod
    def _fix_onnx_less_type_mismatch() -> None:
        """修复 ONNX 导出时 Less 节点类型不匹配的问题。

        在 model_quant.onnx 中，arange 输出 FLOAT，但 Less 的第二个输入
        convert_element_type_default 输出 INT64，导致 Less 的 T 参数冲突。
        在 arange 后插入 Cast 节点转为 INT64。
        """
        import onnx
        from onnx import helper, TensorProto

        cache_dir = os.path.expanduser(
            os.path.join("~", ".cache", "modelscope", "hub")
        )
        model_quant_path = None
        for root, _dirs, files in os.walk(cache_dir):
            if "model_quant.onnx" in files:
                model_quant_path = os.path.join(root, "model_quant.onnx")
                break

        if not model_quant_path or not os.path.exists(model_quant_path):
            logger.error(
                "未找到 model_quant.onnx，无法修复 ONNX 类型不匹配。"
            )
            return

        model = onnx.load(model_quant_path)
        graph = model.graph

        # 找到 arange 输出节点和 Less 节点
        less_node = None
        arange_output = None
        for node in graph.node:
            if node.op_type == "Less":
                less_node = node
                # Less 的第二个输入是 arange 输出
                arange_output = node.input[1]
                break

        if less_node is None:
            logger.info("未找到 Less 节点，无需修复。")
            return

        # 检查 arange_output 的类型
        arange_output_tensor = None
        for vi in graph.value_info:
            if vi.name == arange_output:
                arange_output_tensor = vi
                break

        if arange_output_tensor is None:
            # 也可能是 graph.input
            for vi in graph.input:
                if vi.name == arange_output:
                    arange_output_tensor = vi
                    break

        if arange_output_tensor is None:
            logger.info("无法找到 arange 输出 tensor 信息，跳过修复。")
            return

        # 创建 cast_name
        cast_output_name = arange_output + "_cast_int64"

        # 插入 Cast 节点：将 FLOAT 转为 INT64
        cast_node = helper.make_node(
            "Cast",
            inputs=[arange_output],
            outputs=[cast_output_name],
            name=arange_output + "_to_int64",
            to=TensorProto.INT64,
        )

        # 修改 Less 节点的第二个输入为 cast 后的输出
        less_node.input[1] = cast_output_name

        # 将 Cast 节点插入到 Less 节点之前
        graph.node.insert(
            list(graph.node).index(less_node), cast_node
        )

        onnx.save(model, model_quant_path)
        logger.info("ONNX 模型文件已修复并保存。")

    async def get_text(self, audio_url: str) -> str:
        try:
            # 使用 run_in_executor 来调用模型进行识别
            loop = asyncio.get_running_loop()
            async with MediaResolver(
                audio_url,
                media_type="audio",
                default_suffix=".wav",
            ).as_path(target_format="wav") as audio:
                res = await loop.run_in_executor(
                    None,  # 使用默认的线程池
                    lambda: cast(SenseVoiceSmall, self.model)(
                        str(audio.path), language="auto", use_itn=True
                    ),
                )

            # res = self.model(audio_url, language="auto", use_itn=True)
            logger.debug(f"SenseVoice识别到的文案：{res}")
            text = rich_transcription_postprocess(res[0])
            if self.is_emotion:
                # 提取第二个匹配的值
                matches = re.findall(r"<\|([^|]+)\|>", res[0])
                if len(matches) >= 2:
                    emotion = matches[1]
                    text = f"(当前的情绪：{emotion}) {text}"
                else:
                    logger.warning("未能提取到情绪信息")
            return text
        except Exception as e:
            logger.error(f"处理音频文件时出错: {e}")
            raise
