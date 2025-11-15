# n8n Provider Implementation

## Overview

This document describes the n8n provider implementation for AstrBot, which enables users to integrate n8n workflow automation with AstrBot's chatbot capabilities.

## Architecture

The n8n provider consists of two main components:

### 1. N8nAPIClient (`astrbot/core/utils/n8n_api_client.py`)

A lightweight HTTP client that handles webhook communication with n8n workflows.

**Key Features:**
- Supports both GET and POST HTTP methods
- Handles streaming and non-streaming responses
- Custom authentication header support
- Lazy ClientSession initialization to avoid event loop issues
- Server-Sent Events (SSE) support for streaming responses

### 2. ProviderN8n (`astrbot/core/provider/sources/n8n_source.py`)

The main provider adapter that implements the AstrBot Provider interface.

**Key Features:**
- Webhook-based workflow execution
- Session management with customizable session ID keys
- Multimodal support (text and images)
- Configurable input/output key mappings for flexibility
- Streaming and non-streaming response modes
- Automatic response parsing into MessageChain format

## Configuration

The n8n provider accepts the following configuration parameters:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `n8n_webhook_url` | string | Yes | - | Webhook URL for the n8n workflow |
| `n8n_http_method` | string | No | "POST" | HTTP method (GET or POST) |
| `n8n_auth_header` | string | No | "" | Authentication header name |
| `n8n_auth_value` | string | No | "" | Authentication value |
| `n8n_output_key` | string | No | "output" | Key to extract workflow output |
| `n8n_input_key` | string | No | "input" | Key to send user input |
| `n8n_session_id_key` | string | No | "sessionId" | Key for session ID |
| `n8n_image_urls_key` | string | No | "imageUrls" | Key for image URLs |
| `n8n_streaming` | boolean | No | false | Enable streaming responses |
| `timeout` | integer | No | 120 | Request timeout in seconds |
| `variables` | object | No | {} | Additional variables to send |

### Example Configuration

```json
{
  "type": "n8n",
  "id": "my_n8n_workflow",
  "enable": true,
  "n8n_webhook_url": "https://your-n8n-instance.com/webhook/abc123",
  "n8n_http_method": "POST",
  "n8n_auth_header": "Authorization",
  "n8n_auth_value": "Bearer your-token-here",
  "n8n_output_key": "result",
  "n8n_input_key": "query",
  "timeout": 60,
  "variables": {
    "language": "zh-CN",
    "model": "gpt-4"
  }
}
```

## n8n Workflow Design

To use the n8n provider effectively, your n8n workflow should:

1. **Accept webhook input** with the following structure:
   ```json
   {
     "input": "user message text",
     "sessionId": "unique-session-identifier",
     "imageUrls": ["http://example.com/image.jpg"],
     "system_prompt": "optional system prompt",
     "custom_variable": "custom value"
   }
   ```

2. **Return output** in one of these formats:
   - Simple string: `"response text"`
   - Object with output key: `{"output": "response text"}`
   - Object with alternative keys: `{"data": "response text"}`, `{"result": "response text"}`, etc.
   - Array of items (will be concatenated)

3. **For streaming responses** (if enabled):
   - Send chunks as Server-Sent Events (SSE)
   - Each chunk should contain `output`, `text`, or `data` field

## Response Parsing

The provider intelligently parses n8n workflow responses:

1. **String responses**: Directly converted to plain text
2. **Object responses**: Extracts the configured output key or falls back to common keys
3. **Array responses**: Processes each item, supporting media objects
4. **Media objects**: Supports images, videos, audio, and files with type detection

Example media object:
```json
{
  "type": "image",
  "url": "https://example.com/image.jpg"
}
```

## Testing

The implementation includes comprehensive test coverage (13 tests):

- Provider registration and initialization
- Configuration validation
- Method implementations (get_models, forget, terminate, etc.)
- Response parsing for various formats
- Error handling

Run tests with:
```bash
uv run pytest tests/test_n8n_provider.py -v
```

## Integration Points

### Dashboard Integration
- Added to provider type mapping in `dashboard/src/views/ProviderPage.vue`
- Icon support in `dashboard/src/utils/providerUtils.js`

### Provider Manager
- Registered in `astrbot/core/provider/manager.py` for dynamic loading

### Documentation
- Added to README.md (Chinese)
- Added to README_en.md (English)

## Use Cases

The n8n provider enables powerful integration scenarios:

1. **Custom AI Workflows**: Build complex multi-step AI workflows in n8n
2. **External API Integration**: Connect to third-party services through n8n
3. **Data Processing**: Process user input through custom data pipelines
4. **Conditional Logic**: Implement complex branching logic in n8n
5. **Multi-Model Orchestration**: Combine multiple AI models in a single workflow

## Limitations

- n8n workflows are stateless by design; session management must be handled in the workflow
- No built-in context history retrieval (implement in your n8n workflow if needed)
- File uploads are sent as URLs (not binary data)

## Security Considerations

- Use HTTPS for webhook URLs in production
- Implement authentication using custom headers
- Validate and sanitize all inputs in your n8n workflow
- Consider rate limiting at the n8n level
- No security vulnerabilities found by CodeQL analysis

## Future Enhancements

Potential improvements for future versions:

- Support for file binary uploads
- Context history integration
- Advanced error handling and retry logic
- Webhook signature validation
- Support for n8n Cloud and self-hosted instances with different authentication methods

## References

- [n8n Official Documentation](https://docs.n8n.io/)
- [n8n Webhook Node Documentation](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/)
- [AstrBot Provider Documentation](https://astrbot.app/)
