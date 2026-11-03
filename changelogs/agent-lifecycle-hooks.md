# Agent lifecycle hooks

- `on_agent_step_start` and `on_agent_step_end` bracket each complete built-in tool-loop step. Step-end handlers receive the complete assistant/tool batch, including tool image messages.
- `on_agent_done` runs once on completion, provider errors, exceptions, cancellation, or step-budget exhaustion. `ContextWrapper.run_end_reason` and `run_error` describe the exit; `response` can be `None` when no final response is available.
- `on_llm_response` handles model replies before delivery. Cleanup without a model reply and synthetic interruption responses do not trigger this hook. Stopped events still reach eligible done handlers.
- Task cancellation propagates through plugin hook dispatch, and response generators close when their consumers exit.
