import base64
import wave
import os
from io import BytesIO
import asyncio
import tempfile
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


async def tencent_silk_to_wav(silk_path: str, output_path: str) -> str:
    import pysilk

    with open(silk_path, "rb") as f:
        input_data = f.read()
        if input_data.startswith(b"\x02"):
            input_data = input_data[1:]
        input_io = BytesIO(input_data)
        output_io = BytesIO()
        pysilk.decode(input_io, output_io, 24000)
        output_io.seek(0)
        with wave.open(output_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(output_io.read())

    return output_path


async def wav_to_tencent_silk(wav_path: str, output_path: str) -> int:
    """返回 duration"""
    try:
        import pilk
    except (ImportError, ModuleNotFoundError) as _:
        raise Exception(
            "pilk 模块未安装，请前往管理面板->控制台->安装pip库 安装 pilk 这个库"
        )
    # with wave.open(wav_path, 'rb') as wav:
    #     wav_data = wav.readframes(wav.getnframes())
    #     wav_data = BytesIO(wav_data)
    #     output_io = BytesIO()
    #     pysilk.encode(wav_data, output_io, 24000, 24000)
    #     output_io.seek(0)

    #     # 在首字节添加 \x02,去除结尾的\xff\xff
    #     silk_data = output_io.read()
    #     silk_data_with_prefix = b'\x02' + silk_data[:-2]

    #     # return BytesIO(silk_data_with_prefix)
    #     with open(output_path, "wb") as f:
    #         f.write(silk_data_with_prefix)

    #     return 0
    with wave.open(wav_path, "rb") as wav:
        rate = wav.getframerate()
        duration = pilk.encode(wav_path, output_path, pcm_rate=rate, tencent=True)
        return duration


async def wav_to_tencent_silk_base64(wav_path: str) -> str:
    """
    将 WAV 文件转为 Silk，并返回 Base64 字符串。
    默认采样率为 24000，输出临时文件为 temp/output.silk。

    参数:
    - wav_path: 输入 .wav 文件路径（需为 PCM 16bit）

    返回:
    - Base64 编码的 Silk 字符串
    - duration: 音频时长（秒）
    """
    try:
        import pilk
    except ImportError as e:
        raise Exception("pysilk 模块未安装，请安装 pysilk") from e

    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
    os.makedirs(temp_dir, exist_ok=True)

    with wave.open(wav_path, "rb") as wav:
        rate = wav.getframerate()

    with tempfile.NamedTemporaryFile(
        suffix=".silk", delete=False, dir=temp_dir
    ) as tmp_file:
        silk_path = tmp_file.name

    try:
        duration = await asyncio.to_thread(
            pilk.encode, wav_path, silk_path, pcm_rate=rate, tencent=True
        )

        with open(silk_path, "rb") as f:
            silk_bytes = await asyncio.to_thread(f.read)
            silk_b64 = base64.b64encode(silk_bytes).decode("utf-8")

        return silk_b64, duration  # 已是秒
    finally:
        if os.path.exists(silk_path):
            os.remove(silk_path)
