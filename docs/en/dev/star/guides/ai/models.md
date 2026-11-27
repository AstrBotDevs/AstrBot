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

`state` supplies context as text, a list, or a dict. Gemini and OpenAI also accept explicit `DecisionInput`; supported media depend on the provider, and ordinary JSON remains business data. Calls use the current decision provider unless you pass `provider_id`.

To answer multiple questions in one request, call `ask({name: question}, state=...)`. Answers use the same keys. Import these types from `astrbot.api.provider`:

| Question type | Configuration | Answer type and main field |
| --- | --- | --- |
| `DecisionBooleanQuestion` | `instructions`: a statement to evaluate. | `DecisionBooleanAnswer.probability`: probability that the statement is true. |
| `DecisionChoiceQuestion` | `instructions` and `criteria`: option IDs mapped to descriptions. | `DecisionChoiceAnswer.choice`: the selected option ID. |
| `DecisionScoreQuestion` | `instructions` and `criteria`: Level descriptions ordered lowest to highest: 2–255 for Gemini, 2–10 for OpenAI and System One. | `DecisionScoreAnswer.score`: a possibly fractional rating from 0 to the number of levels minus 1. |

An unavailable provider, failed request, or invalid response raises `DecisionError`. Pass `default=False` to `yes_no()` to return a fallback value for these errors.

### Using OpenAI Decisions with images

In **Model Providers → Decision**, add the **OpenAI Decisions** template and configure its API key, API base (default `https://api.openai.com/v1`), and model. Use `provider_id="openai_decision"` when calling the decision service.

`DecisionInput` is sent as one user message: text blocks become `input_text` and images become `input_image`, preserving their order. Ordinary text and business JSON keep their existing behavior.

#### Explicit image input

Shared `state` can use `DecisionInput` to interleave text with multiple images. Usage matches the Gemini example below; pass `provider_id="openai_decision"`. OpenAI does not insert separators between adjacent text blocks, so include your own spaces or newlines.

```py
from astrbot.api.provider import DecisionBooleanQuestion, DecisionInput, DecisionMedia

state = DecisionInput(content=[
    "Reference:\n",
    DecisionMedia(type="image", mime_type="image/png", uri="https://example.com/ref.png"),
    "\nCandidate:\n",
    DecisionMedia(type="image", mime_type="image/jpeg", data=jpeg_base64),
])
```

- Only `type="image"` is supported, and `mime_type` must be the image's actual `image/*` type; other media types are rejected. The official Decisions documentation does not list supported image formats, so OpenAI validates the format.
- Provide exactly one of `uri` or `data`. `uri` must be a publicly accessible HTTP(S) image URL; `data` is Base64 without a prefix, and the adapter builds a `data:` URL from `mime_type`. `file_id`, local paths, and `data:` values in `uri` are not supported.
- `resolution` is not supported: any value raises `ValueError` and is never mapped to OpenAI's `detail`. Image `detail` uses the API default, `auto`.
- Each resulting image URL is limited to 1 GiB (the API schema limit). The official Decisions documentation does not list separate image size or count limits; OpenAI validates accessibility, total request size, and image count.

All three question types also accept `DecisionInput` as `instructions`, giving each question its own images; for example, put a shared reference image in `state` and a different candidate image in each question. The same conversion and validation rules apply, and question images share the request's image limits with images in `state`. Text-only `instructions` can remain a string. `yes_no()` and `choose()` accept text questions only; use `ask()` for images.

```py
answers = await self.context.decision.ask(
    {
        "match_a": DecisionBooleanQuestion(DecisionInput(content=[
            "Does this candidate match the reference?\n",
            DecisionMedia(type="image", mime_type="image/png", uri="https://example.com/a.png"),
        ])),
    },
    state=DecisionInput(content=["Reference:\n", reference_image]),
    provider_id="openai_decision",
)
```

Message or tool-call history, prompt-cache controls, and `safety_identifier` are not supported. If the model refuses any question (`refusal`), the whole `ask()` call raises `DecisionError`; a refusal is never reported as false, a zero score, or an empty result. `yes_no(default=...)` keeps its fallback behavior.

### Using Gemini Decisions

In **Model Providers → Decision**, add the **Gemini Decisions** template. Enter a Gemini API key (or an `$ENV_NAME` reference), keep the default API base `https://generativelanguage.googleapis.com/v1beta`, and use model `gemini-decision-1`. AstrBot appends `/decisions` unless the path already ends with it, and sends the key in the `x-goog-api-key` header. Save the provider and use its connection test to check access. The model must be available to your Google API project; configuring a provider does not enable access or quota.

The adapter calls the REST endpoint directly and does not require a Google SDK upgrade. It uses the same timeout, total timeout (including queueing and retries), max concurrency, proxy, and custom-header settings as OpenAI Decisions. For large media, increase `timeout` (default 5 seconds) and `total_timeout` (default 10 seconds) as needed. It runs only when a plugin explicitly calls the decision service; it does not join the main chat flow.

Use the common `ask()`, `choose()`, and `yes_no()` methods above with `provider_id="gemini_decision"`.

Gemini boolean questions use `noul`, the probability of **true** (typically in `[0.01, 0.99]`). `yes_no()` compares that probability with its threshold. The adapter does not expose the optional boolean criteria `true_description` and `false_description`; include those definitions in `instructions` instead.

Requests accept 1–1,000 questions, 2–255 options per choice, and 2–255 score levels (2–10 recommended). Option IDs must be non-empty strings; descriptions may be empty. Invalid inputs raise `ValueError` before sending, and additional wire constraints are enforced by Google's API. Caller question IDs are mapped internally, and answers retain the original keys.

Missing or inconsistent answers fail the whole batch with `DecisionError`. The [official API](https://aistudio.google.com/docs/decisions-api) reports safety blocking as HTTP 400 with `error.code` equal to `safety`, `prohibited_content`, `blocklist`, `image_safety`, or `content_blocked`. HTTP 400 errors include the known `invalid_request` code when present; unknown codes and server messages remain hidden. Errors are sanitized; blocking never becomes an answer. `yes_no(default=...)` retains its explicit fallback behavior.

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

The same `state` works with `ask()` and `choose()`. Each `DecisionMedia` requires its actual `mime_type` and exactly one of `uri` or `data`. For inline media, set `data=base64.b64encode(file_bytes).decode("ascii")`, with no data-URI prefix. The adapter checks inline media size limits from the encoded length (up to 100 MB of decoded bytes per request and 50 MB per PDF) without decoding the payload into memory. The adapter does not read local paths or upload files automatically.

| `type` | Example MIME type | Input |
| --- | --- | --- |
| `image` | `image/png`, `image/jpeg` | Base64 `data` or HTTPS `uri` |
| `audio` | `audio/wav`, `audio/mp3` | Base64 `data` or HTTPS `uri` |
| `video` | `video/mp4` | Base64 `data` or HTTPS `uri` |
| `document` | `application/pdf` | Base64 `data` or HTTPS `uri` |

Gemini accepts public/signed HTTPS URLs (up to 15 MB per external URL) and HTTPS URIs returned by its Files API. YouTube URLs and direct `gs://` URIs are unsupported. Optional `resolution` supports `low`, `medium`, or `high` for images and video, plus `ultra_high` for images only; omit it for audio and PDF. See the [official input reference](https://aistudio.google.com/docs/decisions-api#input) for supported formats and size limits. Google checks the actual file format, availability, and request/media limits.

Malformed explicit input is rejected with `ValueError` before sending; API failures raise `DecisionError`. Tool-call, thought, and conversation-history blocks are not accepted as media content. The OpenAI adapter accepts images only; see "Explicit image input" above for its limits.
