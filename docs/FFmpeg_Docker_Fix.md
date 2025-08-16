# FFmpeg Docker Fix Documentation

This document explains the fix for issue #2284: "Docker预装ffmpeg无法使用" (Docker pre-installed FFmpeg cannot be used).

## Problem Description

The issue occurred when using EdgeTTS adapter in Docker environment:

1. Docker installs `pyffmpeg` and downloads FFmpeg binary to `/root/.pyffmpeg/bin/ffmpeg`
2. The original Dockerfile added this path to `.bashrc` with: `RUN echo 'export PATH=$PATH:/root/.pyffmpeg/bin' >> ~/.bashrc`
3. When Python runs via `CMD ["python", "main.py"]`, it doesn't source `.bashrc`
4. This caused `FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'`

## Root Cause

The PATH modification in `.bashrc` only applies to interactive bash shells, not to processes started directly via `CMD`.

## Solution

### 1. Dockerfile Fix

**Before:**
```dockerfile
RUN echo 'export PATH=$PATH:/root/.pyffmpeg/bin' >> ~/.bashrc
```

**After:**
```dockerfile
ENV PATH=$PATH:/root/.pyffmpeg/bin
```

This ensures the PATH is set for all processes in the container, not just interactive shells.

### 2. Python Code Improvements

Added a robust FFmpeg path resolution system:

#### New Utility: `astrbot/core/utils/ffmpeg_helper.py`

```python
def get_ffmpeg_path() -> str:
    """
    Get the FFmpeg executable path.
    
    First tries to find ffmpeg in PATH, then falls back to known locations.
    """
    # First try PATH
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return "ffmpeg"
    
    # Fall back to common locations
    fallback_paths = [
        "/root/.pyffmpeg/bin/ffmpeg",  # Docker pyffmpeg location
        "/usr/local/bin/ffmpeg",      # Common installation path
        "/usr/bin/ffmpeg",            # System installation path
        "/opt/bin/ffmpeg",            # Alternative installation path
    ]
    
    for path in fallback_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path
    
    return "ffmpeg"  # Let caller handle the error
```

#### Updated Files

1. **`astrbot/core/provider/sources/edge_tts_source.py`**:
   - Import: `from astrbot.core.utils.ffmpeg_helper import get_ffmpeg_path`
   - Changed: `"ffmpeg"` → `get_ffmpeg_path()`

2. **`astrbot/core/utils/tencent_record_helper.py`**:
   - Same changes for consistency

## Testing

### Unit Tests
- ✅ FFmpeg path resolution logic
- ✅ Fallback path functionality  
- ✅ Import compatibility

### Integration Tests
- ✅ Development environment compatibility
- ⚠️ Full Docker testing requires building image

### Manual Testing in Docker

To test the fix manually:

1. Build the Docker image:
   ```bash
   docker build -t astrbot-test .
   ```

2. Run the container:
   ```bash
   docker run -it astrbot-test bash
   ```

3. Test FFmpeg availability:
   ```bash
   # Should work now
   ffmpeg -version
   
   # Test Python integration
   python -c "
   from astrbot.core.utils.ffmpeg_helper import get_ffmpeg_path
   print('FFmpeg path:', get_ffmpeg_path())
   "
   ```

4. Test EdgeTTS:
   - Create EdgeTTS adapter in WebUI
   - Click "测试可用性" (Test Availability)
   - Should not get "No such file or directory: 'ffmpeg'" error

## Backwards Compatibility

- ✅ Existing installations continue to work
- ✅ Non-Docker environments unaffected
- ✅ Falls back gracefully when FFmpeg not found

## Benefits

1. **Immediate Fix**: ENV PATH setting resolves the primary issue
2. **Robust Fallback**: Python code handles edge cases
3. **Centralized Logic**: Single utility for FFmpeg path resolution
4. **Better Error Handling**: Consistent behavior across modules
5. **Future-Proof**: Easy to add more fallback paths if needed

## Files Modified

- `Dockerfile` - Fixed PATH environment variable
- `astrbot/core/utils/ffmpeg_helper.py` - New utility (added)
- `astrbot/core/provider/sources/edge_tts_source.py` - Use helper utility
- `astrbot/core/utils/tencent_record_helper.py` - Use helper utility
- `tests/test_ffmpeg_integration.py` - Integration test (added)

## Related Issues

Fixes #2284: [Bug]Docker预装ffmpeg无法使用