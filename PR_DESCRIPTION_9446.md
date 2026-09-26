# Issue #9446 - SSL Verification Downgrade Vulnerability Fix

## 🔐 Security Fix

This PR fixes a critical security vulnerability where `download_image_by_url()` and `download_file()` 
would silently downgrade SSL certificate verification to `CERT_NONE` on SSL errors, allowing 
man-in-the-middle (MITM) attacks.

### Vulnerability Details

**Before Fix:**
- When SSL certificate verification failed, the code would catch the exception and retry with `ssl.CERT_NONE`
- This fallback behavior was automatic and silent (only logged a warning)
- Attackers could exploit this by triggering certificate errors to force insecure connections

**After Fix:**
- SSL certificate verification is always enforced
- SSL errors raise exceptions immediately without fallback
- No automatic downgrade to insecure connections

## 🔧 Changes

### Modified Functions

#### `download_image_by_url()` (lines 116-144)
- **Removed:** SSL fallback try-except block that would retry with `CERT_NONE`
- **Behavior:** SSL certificate errors now raise immediately instead of falling back to insecure mode
- **Impact:** Functions calling this must handle SSL exceptions explicitly

#### `download_file()` (lines 250-291)
- **Removed:** SSL fallback logic
- **Changed:** Default parameter value `allow_insecure_ssl_fallback=False` (was `True`)
- **Updated:** Parameter documentation to indicate it's deprecated and ignored
- **Behavior:** Always enforces SSL verification regardless of parameter value

#### `download_dashboard()` (lines 452-549)
- **Updated:** Parameter documentation for `allow_insecure_ssl_fallback` 
- **Documentation:** Now indicates the parameter is deprecated and ignored
- **Note:** Parameter retained for backward compatibility but has no effect

### Breaking Change ⚠️

**Parameter default changed:** `download_file(allow_insecure_ssl_fallback=False)` (was `True`)

**Impact:** Code that relied on automatic SSL verification downgrade will now raise exceptions 
for certificate errors. This is intentional security hardening.

**Migration Guide:**
- If you encounter SSL certificate errors, do NOT disable verification
- For self-signed certificates: Add them to your system's CA certificate store
- For development/testing: Use proper certificate configuration instead of bypassing verification
- The `allow_insecure_ssl_fallback` parameter is now deprecated and ignored

## ✅ Testing

### Test Coverage
- **13 new SSL verification tests** in `tests/unit/test_io_ssl_verification.py`
- **SSL error handling tests** in `tests/unit/test_io_download_file.py`
- All existing download tests updated and passing

### Test Results
- ✅ SSL errors raise immediately without retry
- ✅ HTTPS downloads with valid certificates work correctly
- ✅ HTTP (non-encrypted) URLs continue to work
- ✅ Both `download_image_by_url()` and `download_file()` enforce SSL verification
- ✅ Deprecated parameter is properly ignored

## 📝 Documentation Updates

### Updated Documentation
1. **`download_file()`** - Parameter documentation updated to indicate deprecation
2. **`download_dashboard()`** - Parameter documentation updated to indicate deprecation
3. **Test files** - Include references to Issue #9446 with detailed explanations

### Parameter Documentation
```python
allow_insecure_ssl_fallback: Deprecated parameter, ignored. SSL certificate
    verification is always enforced for security.
```

## 🔍 Security Considerations

### Why This Fix Matters
1. **Prevents MITM Attacks:** Ensures all HTTPS connections verify server identity
2. **No Silent Failures:** SSL errors are visible and must be handled explicitly
3. **Defense in Depth:** Removes automatic fallback to insecure mode
4. **Compliance:** Aligns with security best practices and standards

### Affected Code Paths
- Dashboard downloads from official repositories
- Plugin downloads
- Image downloads from external URLs
- Any code using `download_file()` or `download_image_by_url()`

## 📋 Checklist

- [x] Security vulnerability fixed
- [x] Breaking change documented
- [x] All tests passing (13 new SSL tests added)
- [x] Documentation updated for affected functions
- [x] Migration guide provided
- [x] No new dependencies introduced
- [x] Code reviewed for security implications

## 🔗 Related

- Issue: #9446
- Related commits: `218e88755` (earlier SSL error handling work)
- Security: High priority - MITM vulnerability
