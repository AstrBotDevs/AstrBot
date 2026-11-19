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

should_route = await self.context.decision.matches(
    question="Does this message request a refund?",
    expected_answer=True,
    confidence_threshold=0.85,
    state=event.message_str,
)

strategy = await self.context.decision.choose(
    question="Which reply strategy should be used?",
    criteria={"short": "A brief reply", "detailed": "A detailed reply"},
    state="The user asks for step-by-step troubleshooting.",
)
print(strategy.choice)
```

`yes_no()` returns a `bool`: `True` when the affirmative probability meets `threshold`. `choose()` returns a `DecisionChoiceAnswer`; read `.choice` for the selected value.

`matches()` checks the selected yes or no answer and the model's confidence in it. It returns `True` only when the answer equals `expected_answer` and confidence meets or exceeds `confidence_threshold`.

`state` accepts text, a list, a dict, or a prepared image (`ResolvedMediaData`) for models with image input. Calls use the current decision provider unless you pass `provider_id`.

To answer multiple questions in one request, call `ask({name: question}, state=...)`. Answers use the same keys. Import these types from `astrbot.api.provider`:

| Question type | Configuration | Answer type and main field |
| --- | --- | --- |
| `DecisionBooleanQuestion` | `instructions`: a statement to evaluate. | `DecisionBooleanAnswer.probability`: probability that the statement is true. |
| `DecisionChoiceQuestion` | `instructions` and `criteria`: option IDs mapped to descriptions. | `DecisionChoiceAnswer.choice`: the selected option ID. |
| `DecisionScoreQuestion` | `instructions` and `criteria`: 2–10 level descriptions, lowest to highest. | `DecisionScoreAnswer.score`: a possibly fractional rating from 0 to the number of levels minus 1. |

An unavailable provider, failed request, or invalid response raises `DecisionError`. Pass `default=False` to `yes_no()` to return a fallback value for these errors.

