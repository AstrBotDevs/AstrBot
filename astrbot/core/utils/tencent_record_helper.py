import wave
from io import BytesIO


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
