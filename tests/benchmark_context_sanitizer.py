"""Benchmark suite for ContextSanitizer (Issue #10195).

Measures:
1. Token reduction percentage across multi-turn sessions (3, 5, 10 turns).
2. Bulky tool output pruning efficiency.
3. Execution latency and CPU overhead (1000 iterations).
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from astrbot.core.agent.context.sanitizer import ContextSanitizer
from astrbot.core.agent.context.token_counter import EstimateTokenCounter
from astrbot.core.agent.message import (
    AssistantMessageSegment,
    Message,
    TextPart,
    ThinkPart,
    ToolCall,
    ToolCallMessageSegment,
)


def generate_conversation(
    num_turns: int, reasoning_tokens_per_turn: int = 800
) -> list[Message]:
    """Generate a realistic multi-turn conversation with reasoning chains and occasional tool calls."""
    messages: list[Message] = [
        Message(
            role="system", content="You are a helpful and knowledgeable AI assistant."
        )
    ]

    simulated_thought = "Let me reason through this step by step: " + (
        "analyzing constraints, checking knowledge base, forming hypothesis, verifying facts. "
        * (reasoning_tokens_per_turn // 15)
    )

    for i in range(1, num_turns + 1):
        # User message
        messages.append(
            Message(
                role="user",
                content=f"User query for turn {i}: What are the key details?",
            )
        )

        if i % 3 == 0:
            # Tool call turn
            tool_id = f"call_{i}"
            messages.append(
                AssistantMessageSegment(
                    role="assistant",
                    content=[ThinkPart(think=simulated_thought)],
                    tool_calls=[
                        ToolCall(
                            id=tool_id,
                            function=ToolCall.FunctionBody(
                                name="search_database",
                                arguments=f'{{"query": "turn {i}"}}',
                            ),
                        )
                    ],
                )
            )
            # Bulky tool response (e.g. 2KB JSON)
            raw_tool_json = (
                '{"status": "success", "results": ['
                + ", ".join(
                    f'{{"id": {j}, "data": "record {j} with details and payload"}}'
                    for j in range(25)
                )
                + "]}"
            )
            messages.append(
                ToolCallMessageSegment(
                    role="tool", tool_call_id=tool_id, content=raw_tool_json
                )
            )

        # Assistant final response
        messages.append(
            AssistantMessageSegment(
                role="assistant",
                content=[
                    ThinkPart(think=simulated_thought),
                    TextPart(
                        text=f"This is the concise and helpful answer for turn {i}."
                    ),
                ],
            )
        )

    # Current user query initiating the next turn
    messages.append(
        Message(
            role="user",
            content="Current active question: can you summarize our conversation?",
        )
    )
    return messages


def run_benchmark():
    counter = EstimateTokenCounter()
    sanitizer_thoughts_only = ContextSanitizer(
        sanitize_historical_thoughts=True,
        sanitize_historical_tools=False,
    )
    sanitizer_full = ContextSanitizer(
        sanitize_historical_thoughts=True,
        sanitize_historical_tools=True,
        max_historical_tool_result_chars=300,
    )

    print("=" * 80)
    print("  ContextSanitizer Benchmark Report (AstrBot Multi-Turn Session)")
    print("=" * 80)
    print(
        f"{'Turns':<8} | {'Raw Tokens':<12} | {'Sanitized (CoT)':<16} | {'Reduction %':<12} | {'Full Sanitize':<14} | {'Full Red %':<10}"
    )
    print("-" * 80)

    for turns in [3, 5, 10, 15]:
        conversation = generate_conversation(
            num_turns=turns, reasoning_tokens_per_turn=800
        )
        raw_tokens = counter.count_tokens(conversation)

        # Sanitize thoughts only
        sanitized_cot = sanitizer_thoughts_only.sanitize(conversation)
        cot_tokens = counter.count_tokens(sanitized_cot)
        reduction_cot = (1.0 - cot_tokens / raw_tokens) * 100.0

        # Full sanitize (thoughts + tools)
        sanitized_full = sanitizer_full.sanitize(conversation)
        full_tokens = counter.count_tokens(sanitized_full)
        reduction_full = (1.0 - full_tokens / raw_tokens) * 100.0

        print(
            f"{turns:<8} | {raw_tokens:<12} | {cot_tokens:<16} | {reduction_cot:>10.2f}% | {full_tokens:<14} | {reduction_full:>8.2f}%"
        )

    print("=" * 80)
    print("  Latency & Computational Overhead (1000 iterations)")
    print("=" * 80)

    test_conv = generate_conversation(num_turns=10, reasoning_tokens_per_turn=800)
    iterations = 1000

    start_time = time.perf_counter()
    for _ in range(iterations):
        _ = sanitizer_full.sanitize(test_conv)
    total_time = time.perf_counter() - start_time
    avg_latency_ms = (total_time / iterations) * 1000

    print(f"Total time for {iterations} runs: {total_time:.4f} s")
    print(f"Average latency per sanitize:   {avg_latency_ms:.4f} ms (< 0.5 ms budget)")
    print(f"Throughput:                     {iterations / total_time:.1f} ops/sec")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmark()
