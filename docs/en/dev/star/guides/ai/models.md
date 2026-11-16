# Models

Call a model to generate a reply or make a structured decision. For tool execution or conversation history, see [Agents](./agent.md).

## Chat Models {#chat-models}

### Getting the Chat Model ID for the Current Session

```py
umo = event.unified_msg_origin
provider_id = await self.context.get_current_chat_provider_id(umo=umo)
```

### Generate a reply

```py
llm_resp = await self.context.llm_generate(
    chat_provider_id=provider_id,  # Chat model ID
    prompt="Hello, world!",
)
# print(llm_resp.completion_text) # Get the returned text
```

## Decision Models {#decision-models}

Use a decision provider to decide whether to reply or which action to take. Configure one under **Providers → Decision** in the WebUI, then call `self.context.decision`.

```py
should_reply = await self.context.decision.yes_no(
    question="Should the assistant reply to this message?",
    state="I cannot log in; every request returns 500.",
    threshold=0.7,
)

strategy = await self.context.decision.choose(
    question="Which reply strategy should be used?",
    criteria={"short": "A brief reply", "detailed": "A detailed reply"},
    state="The user asks for step-by-step troubleshooting.",
)
print(strategy.choice)
```

`yes_no()` returns a `bool`: `True` when the affirmative probability meets `threshold`. `choose()` returns a `DecisionChoiceAnswer`; read `.choice` for the selected value.

`state` supplies context as text, a list, or a dict. Gemini also accepts explicit multimodal `DecisionInput`; ordinary JSON remains business data. Calls use the current decision provider unless you pass `provider_id`.

To answer multiple questions in one request, call `ask({name: question}, state=...)`. Answers use the same keys. Import these types from `astrbot.api.provider`:

| Question type | Configuration | Answer type and main field |
| --- | --- | --- |
| `DecisionBooleanQuestion` | `instructions`: a statement to evaluate. | `DecisionBooleanAnswer.probability`: probability that the statement is true. |
| `DecisionChoiceQuestion` | `instructions` and `criteria`: option IDs mapped to descriptions. | `DecisionChoiceAnswer.choice`: the selected option ID. |
| `DecisionScoreQuestion` | `instructions` and `criteria`: Level descriptions ordered lowest to highest: 2–255 for Gemini, 2–10 for OpenAI and System One. | `DecisionScoreAnswer.score`: a possibly fractional rating from 0 to the number of levels minus 1. |

An unavailable provider, failed request, or invalid response raises `DecisionError`. Pass `default=False` to `yes_no()` to return a fallback value for these errors.

### Using Gemini Decisions

In **Model Providers → Decision**, add the **Gemini Decisions** template. Enter a Gemini API key (or an `$ENV_NAME` reference), keep the default API base `https://generativelanguage.googleapis.com/v1beta`, and use model `gemini-decision-1`. AstrBot appends `/decisions` unless the path already ends with it, and sends the key in the `x-goog-api-key` header. Save the provider and use its connection test to check access. The model must be available to your Google API project; configuring a provider does not enable access or quota.

The adapter calls the REST endpoint directly and does not require a Google SDK upgrade. It uses the same timeout, total timeout (including queueing and retries), max concurrency, proxy, and custom-header settings as OpenAI Decisions. For large media, increase `timeout` (default 5 seconds) and `total_timeout` (default 10 seconds) as needed. It runs only when a plugin explicitly calls the decision service; it does not join the main chat flow.

Use the common `ask()`, `choose()`, and `yes_no()` methods above with `provider_id="gemini_decision"`.

Gemini boolean questions use `noul`, the probability of **true**, in `[0.01, 0.99]`. `yes_no()` compares that probability with its threshold; thresholds above `0.99` cannot match. Gemini's boolean confidence is `max(p, 1-p)`. The adapter does not expose the optional boolean criteria `true_description` and `false_description`; include those definitions in `instructions` instead. Choice answers must select the highest-probability option; exact ties use the first ID in UTF-8 byte order. Score confidence is the largest level probability.

Requests accept 1–1,000 questions, 2–255 options per choice, and 2–255 score levels (2–10 recommended). Choice IDs contain 1–128 characters, at most 512 UTF-8 bytes; internal ASCII spaces, combining marks, and variation selectors are allowed. Surrounding/non-ASCII whitespace and Unicode Other categories (`Cc`, `Cf`, `Cs`, `Co`, `Cn`), including zero-width format and private-use characters, are rejected. Descriptions may be empty. Invalid inputs raise `ValueError` before sending. Caller question IDs are mapped internally, and answers retain the original keys.

Missing or inconsistent answers fail the whole batch with `DecisionError`. The [official API](https://aistudio.google.com/docs/decisions-api) reports safety blocking as HTTP 400 with `error.code` equal to `safety`, `prohibited_content`, `blocklist`, `image_safety`, or `content_blocked`. The adapter also recognizes a non-empty string `prompt_feedback.block_reason` and ignores unknown feedback shapes. HTTP 400 errors include the known `invalid_request` code when present; unknown codes and server messages remain hidden. Errors are sanitized; blocking never becomes an answer. `yes_no(default=...)` retains its explicit fallback behavior.

Gemini sends ordinary dict/list state as JSON text, including empty containers. Omitted state, `None`, and an empty string become the JSON text `"{}"` because the API rejects empty input. Unsupported or non-serializable values and `NaN`/`Infinity` are rejected. Use `DecisionInput` below to send media explicitly; question instructions remain text-only.

#### Explicit multimodal input

Import `DecisionInput` and `DecisionMedia` from `astrbot.api.provider`. `DecisionInput.content` is a non-empty ordered list of text strings and `DecisionMedia` objects. Gemini concatenates adjacent text blocks without inserting separators, so include your own spaces or newlines.

```py
from astrbot.api.provider import DecisionInput, DecisionMedia

photo = DecisionInput(content=[
    "Inspect this product photo.\n",
    DecisionMedia(
        type="image",
        uri="https://example.com/product.png",  # Replace with an accessible media URL.
        mime_type="image/png",
        resolution="low",
    ),
])

has_damage = await self.context.decision.yes_no(
    "Does the product have visible damage?",
    state=photo,
    provider_id="gemini_decision",
)
```

The same `state` works with `ask()` and `choose()`. Each `DecisionMedia` requires its actual `mime_type` and exactly one of `uri` or `data`. For inline media, set `data=base64.b64encode(file_bytes).decode("ascii")`, with no data-URI prefix. Before decoding, the adapter checks inline media sizes: up to 100 MB of decoded bytes per request and 50 MB per PDF. The adapter does not read local paths or upload files automatically.

| `type` | Example MIME type | Input |
| --- | --- | --- |
| `image` | `image/png`, `image/jpeg` | Base64 `data` or HTTPS `uri` |
| `audio` | `audio/wav`, `audio/mp3` | Base64 `data` or HTTPS `uri` |
| `video` | `video/mp4` | Base64 `data` or HTTPS `uri` |
| `document` | `application/pdf` | Base64 `data` or HTTPS `uri` |

Gemini accepts public/signed HTTPS URLs (up to 15 MB per external URL) and HTTPS URIs returned by its Files API. YouTube URLs and direct `gs://` URIs are unsupported. Optional `resolution` supports `low`, `medium`, or `high` for images and video, plus `ultra_high` for images only; omit it for audio and PDF. See the [official input reference](https://aistudio.google.com/docs/decisions-api#input) for supported formats and size limits. Google checks the actual file format, availability, and request/media limits.

Malformed explicit input is rejected with `ValueError` before sending; API failures raise `DecisionError`. Tool-call, thought, and conversation-history blocks are not accepted as media content. The current OpenAI adapter explicitly rejects `DecisionInput` with `ValueError`; use text/business JSON there.
