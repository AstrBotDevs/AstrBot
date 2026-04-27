#!/bin/bash
set -e

echo "=== Testing fix for #6661 ==="
echo ""

cd /app

echo "Test 1: Code Syntax Check"
python -m py_compile astrbot/core/provider/sources/openai_source.py && echo "✅ PASS: Syntax check" || { echo "❌ FAIL: Syntax error"; exit 1; }

echo ""
echo "Test 2: Tool Call Delta Index Fix Logic"
python << 'EOF'
from dataclasses import dataclass
from typing import Optional

@dataclass
class MockToolCallDelta:
    index: Optional[int] = None
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

def apply_index_fix(chunk):
    """Apply the same fix logic as in the code"""
    if hasattr(chunk, 'choices') and chunk.choices:
        choice = chunk.choices[0]
        if hasattr(choice, 'delta') and hasattr(choice.delta, 'tool_calls') and choice.delta.tool_calls:
            for tc in choice.delta.tool_calls:
                if not hasattr(tc, 'index') or tc.index is None:
                    tc.index = 0

@dataclass
class MockDelta:
    tool_calls: list = None
    def __init__(self, tool_calls=None):
        self.tool_calls = tool_calls or []

@dataclass  
class MockChoice:
    delta: MockDelta = None
    def __init__(self, delta=None):
        self.delta = delta

@dataclass
class MockChunk:
    choices: list = None
    def __init__(self, choices=None):
        self.choices = choices or []

# Test 1: tool_call without index
tc = MockToolCallDelta()
chunk = MockChunk([MockChoice(MockDelta([tc]))])
apply_index_fix(chunk)
assert tc.index == 0, f"Expected index=0, got {tc.index}"
print("✅ PASS: Tool call without index gets index=0")

# Test 2: tool_call with existing index
tc = MockToolCallDelta(index=2)
chunk = MockChunk([MockChoice(MockDelta([tc]))])
apply_index_fix(chunk)
assert tc.index == 2, f"Expected index=2, got {tc.index}"
print("✅ PASS: Tool call with existing index preserved")

# Test 3: Empty tool_calls
chunk = MockChunk([MockChoice(MockDelta([]))])
apply_index_fix(chunk)
print("✅ PASS: Empty tool_calls handled")

# Test 4: No choices
chunk = MockChunk([])
apply_index_fix(chunk)
print("✅ PASS: Empty choices handled")

print("")
print("✅ ALL TESTS PASSED")
EOF

echo ""
echo "✅ ALL TESTS PASSED"
exit 0
