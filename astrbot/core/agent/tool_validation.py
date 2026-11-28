"""Validate tool arguments without letting tool-supplied schemas block the runner."""

import asyncio
import json
import sys
from contextlib import suppress
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.exceptions import Unresolvable

_VALIDATION_TIMEOUT = 3.0
_MAX_WORKER_INPUT_BYTES = 1_048_576


def _validation_error(schema: dict, arguments: dict) -> str | None:
    # Use local references only; schema validation must not make network requests.
    validator = validator_for(schema, default=Draft202012Validator)(
        schema, registry=Registry()
    )
    try:
        error = next(validator.iter_errors(arguments), None)
    except Unresolvable:
        return "Tool input schema has an unresolved reference."
    if error is not None:
        return (
            "Tool arguments do not match the provided input schema "
            f"({error.json_path[:120]}: {error.validator})."
        )
    return None


async def validate_tool_arguments(schema: dict, arguments: object) -> None:
    """Check an argument object against a tool's declared input schema.

    Args:
        schema: JSON Schema supplied by the tool registration.
        arguments: Arguments emitted by the model or updated by a hook.

    Raises:
        ValueError: Arguments are invalid or validation cannot safely complete.
    """
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object.")

    # Regexes and combinators can both run unbounded; a thread cannot be killed.
    payload = json.dumps([schema, arguments]).encode()
    if len(payload) > _MAX_WORKER_INPUT_BYTES:
        raise ValueError("Tool schema and arguments exceed the validation size limit.")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).resolve()),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(
            process.communicate(payload), _VALIDATION_TIMEOUT
        )
    except TimeoutError as exc:
        raise ValueError("Tool input schema validation timed out.") from exc
    finally:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
    if process.returncode != 0:
        raise ValueError("Tool input schema validation failed.")
    if error := json.loads(output):
        raise ValueError(error)


if __name__ == "__main__":
    schema, arguments = json.load(sys.stdin)
    json.dump(_validation_error(schema, arguments), sys.stdout)
