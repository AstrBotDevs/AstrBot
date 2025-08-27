#!/usr/bin/env python3
"""
Integration test for FFmpeg availability in Docker environment.
This should be run inside the Docker container to verify the fix.
"""
import sys
import os
import asyncio
import tempfile
import uuid
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, '/AstrBot')

from astrbot.core.provider.sources.edge_tts_source import ProviderEdgeTTS
from astrbot.core.utils.ffmpeg_helper import get_ffmpeg_path, get_ffmpeg_path_or_none


def create_test_mp3():
    """Create a simple test MP3 file (actually just a dummy file)."""
    temp_dir = tempfile.mkdtemp()
    mp3_path = os.path.join(temp_dir, f"test_{uuid.uuid4()}.mp3")
    
    # Create a dummy file (in real usage, this would be a proper MP3 from edge-tts)
    with open(mp3_path, 'wb') as f:
        f.write(b'dummy mp3 content for testing')
    
    return temp_dir, mp3_path


async def test_ffmpeg_integration():
    """Test the full integration including EdgeTTS provider."""
    print("=== Docker FFmpeg Integration Test ===")
    success = True
    
    # Test 1: FFmpeg path resolution
    print("1. Testing FFmpeg path resolution...")
    try:
        ffmpeg_path = get_ffmpeg_path()
        print(f"   ✓ FFmpeg path: {ffmpeg_path}")
        
        ffmpeg_optional = get_ffmpeg_path_or_none()
        print(f"   ✓ FFmpeg optional: {ffmpeg_optional}")
        
        if ffmpeg_optional is None:
            print("   ⚠ FFmpeg not found - this may be expected in non-Docker environment")
        
    except Exception as e:
        print(f"   ✗ FFmpeg path resolution failed: {e}")
        success = False
    
    # Test 2: FFmpeg executable test
    print("2. Testing FFmpeg executable...")
    try:
        ffmpeg_cmd = get_ffmpeg_path()
        process = await asyncio.create_subprocess_exec(
            ffmpeg_cmd,
            "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            version_line = stdout.decode().split('\n')[0] if stdout else "Unknown"
            print(f"   ✓ FFmpeg version: {version_line}")
        else:
            print(f"   ✗ FFmpeg execution failed with return code: {process.returncode}")
            print(f"     stderr: {stderr.decode()}")
            success = False
            
    except FileNotFoundError:
        print("   ✗ FFmpeg executable not found")
        success = False
    except Exception as e:
        print(f"   ✗ FFmpeg execution test failed: {e}")
        success = False
    
    # Test 3: Test EdgeTTS provider initialization (without actual TTS)
    print("3. Testing EdgeTTS provider initialization...")
    try:
        provider_config = {
            "edge-tts-voice": "zh-CN-XiaoxiaoNeural",
            "timeout": 30
        }
        provider_settings = {}
        
        edge_tts = ProviderEdgeTTS(provider_config, provider_settings)
        print("   ✓ EdgeTTS provider initialized successfully")
        
    except Exception as e:
        print(f"   ✗ EdgeTTS provider initialization failed: {e}")
        success = False
    
    # Test 4: Test audio conversion (mock)
    print("4. Testing audio conversion capabilities...")
    try:
        from astrbot.core.utils.tencent_record_helper import convert_to_pcm_wav
        
        temp_dir, test_mp3 = create_test_mp3()
        wav_path = os.path.join(temp_dir, f"test_{uuid.uuid4()}.wav")
        
        try:
            # This will fail because it's not a real MP3, but we can test the ffmpeg path logic
            await convert_to_pcm_wav(test_mp3, wav_path)
        except Exception as e:
            # Expected to fail with dummy file, but should not fail due to missing ffmpeg
            if "No such file or directory: 'ffmpeg'" in str(e):
                print(f"   ✗ FFmpeg still not found in convert_to_pcm_wav: {e}")
                success = False
            else:
                print(f"   ✓ convert_to_pcm_wav found ffmpeg (failed for other reasons: {type(e).__name__})")
        
        # Clean up
        import shutil
        shutil.rmtree(temp_dir)
        
    except ImportError as e:
        print(f"   ⚠ Could not import convert_to_pcm_wav: {e}")
    except Exception as e:
        print(f"   ✗ Audio conversion test failed: {e}")
        success = False
    
    return success


async def main():
    """Main test function."""
    print("This test is designed to run inside the Docker container.")
    print("In development environment, some tests may fail due to missing FFmpeg.\n")
    
    success = await test_ffmpeg_integration()
    
    if success:
        print("\n🎉 All tests passed! FFmpeg integration is working correctly.")
        return 0
    else:
        print("\n❌ Some tests failed. Check the output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))