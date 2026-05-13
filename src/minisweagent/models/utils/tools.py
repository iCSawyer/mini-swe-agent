"""Tool registry. Every tool compiles its args down to a single bash command,
so the Environment layer (LocalEnvironment / DockerEnvironment / ...) does not need to change.

Add new tools by defining a class here and registering it in BUILTIN.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Tool(Protocol):
    name: str
    schema: dict  # OpenAI function tool schema

    def validate(self, args: dict) -> str | None:
        """Return a human-readable error message if args are invalid, else None."""
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


BUILTIN: dict[str, type[Tool]] = {
    "bash": BashTool,
}


def resolve_tools(specs: list[str]) -> dict[str, Tool]:
    """Resolve a list of builtin tool names into a name->Tool registry."""
    out: dict[str, Tool] = {}
    for spec in specs:
        if spec not in BUILTIN:
            raise ValueError(f"Unknown tool '{spec}'. Available: {sorted(BUILTIN)}")
        tool = BUILTIN[spec]()
        out[tool.name] = tool
    return out
