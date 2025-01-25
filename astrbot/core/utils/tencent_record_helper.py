import wave
from io import BytesIO

async def tencent_silk_to_wav(silk_path: str, output_path: str) -> str:
    import pilk
    
    with open(silk_path, "rb") as f:
        pcm_path = f"{output_path}.pcm"
        pilk.decode(silk_path, pcm_path)
        
        with open(pcm_path, "rb") as pcm:
            with wave.open(output_path, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(pcm.read())
            
    return output_path

async def wav_to_tencent_silk(wav_path: str, output_path: str) -> int:
    '''返回 duration'''
    import pilk
    
    # wav to pcm
    with wave.open(wav_path, 'rb') as wav:
        pcm_path = f"{wav_path}.pcm"
        with open(pcm_path, "wb") as f:
            f.write(wav.readframes(wav.getnframes()))
        
        return pilk.encode(pcm_path, output_path, pcm_rate=24000, tencent=True)