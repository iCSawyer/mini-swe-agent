"""Tool registry. Every tool compiles its args down to a single bash command,
so the Environment layer (LocalEnvironment / DockerEnvironment / ...) does not need to change.

Add new tools by defining a class here and registering it in BUILTIN.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class Tool(Protocol):
    name: str
    schema: dict  # OpenAI function tool schema

    def validate(self, args: dict) -> str | None:
        """Return an error message if invalid, else None. Falsy = valid; non-empty string
        is surfaced verbatim to the model."""
        ...

    def to_command(self, args: dict) -> str: ...


class BashTool:
    name = "bash"
    schema = {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Execute a bash command",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "The bash command to execute"}},
                "required": ["command"],
            },
        },
    }

    def validate(self, args: dict) -> str | None:
        if "command" not in args:
            return "Missing 'command' argument in bash tool call."
        if not isinstance(args["command"], str):
            return "'command' argument must be a string."
        return None

    def to_command(self, args: dict) -> str:
        return args["command"]


class SubmitTool:
    name = "submit"
    schema = {
        "type": "function",
        "function": {
            "name": "submit",
            "description": (
                "Finish the task and return your final answer. "
                "The agent exits after this call, so only use it when you are done."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string", "description": "Final answer to return to the user."}
                },
                "required": ["answer"],
            },
        },
    }

    def validate(self, args: dict) -> str | None:
        if "answer" not in args:
            return "Missing 'answer' argument in submit tool call."
        if not isinstance(args["answer"], str):
            return "'answer' argument must be a string."
        return None

    def to_command(self, args: dict) -> str:
        return f"echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && printf %s {shlex.quote(args['answer'])}"



BUILTIN: dict[str, Callable[[], Tool]] = {
    "bash": BashTool,
    "submit": SubmitTool,
}


def resolve_tools(specs: list[str]) -> dict[str, Tool]:
    """Resolve a list of builtin tool names into a name->Tool registry."""
    if not specs:
        raise ValueError(
            "`tools` must contain at least one tool."
            f"Available: {sorted(BUILTIN)}."
        )
    out: dict[str, Tool] = {}
    for spec in specs:
        if spec not in BUILTIN:
            raise ValueError(f"Unknown tool '{spec}'. Available: {sorted(BUILTIN)}")
        tool = BUILTIN[spec]()
        out[tool.name] = tool
    return out
