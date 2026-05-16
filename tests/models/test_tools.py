"""Tests for the fork-specific tool registry in minisweagent.models.utils.tools.

Covers BashTool / SubmitTool semantics, resolve_tools resolution + validation,
and the BUILTIN extension contract used by user code (see mini-usage/extra_tools.py).
"""

import subprocess

import pytest

from minisweagent.environments.local import LocalEnvironment
from minisweagent.exceptions import Submitted
from minisweagent.models.utils.tools import (
    BUILTIN,
    BashTool,
    SubmitTool,
    Tool,
    resolve_tools,
)


# --- BashTool ---------------------------------------------------------------


class TestBashTool:
    def test_validate_accepts_string_command(self):
        assert BashTool().validate({"command": "ls"}) is None

    def test_validate_rejects_missing_command(self):
        msg = BashTool().validate({})
        assert msg and "command" in msg.lower()

    def test_validate_rejects_non_string_command(self):
        msg = BashTool().validate({"command": 42})
        assert msg and "string" in msg.lower()

    def test_to_command_is_passthrough(self):
        assert BashTool().to_command({"command": "echo hi"}) == "echo hi"

    def test_schema_function_name_matches_tool_name(self):
        assert BashTool.schema["function"]["name"] == BashTool.name


# --- SubmitTool -------------------------------------------------------------


class TestSubmitTool:
    def test_validate_accepts_string_answer(self):
        assert SubmitTool().validate({"answer": "done"}) is None

    def test_validate_rejects_missing_answer(self):
        msg = SubmitTool().validate({})
        assert msg and "answer" in msg.lower()

    def test_validate_rejects_non_string_answer(self):
        msg = SubmitTool().validate({"answer": ["a", "b"]})
        assert msg and "string" in msg.lower()

    def test_schema_function_name_matches_tool_name(self):
        assert SubmitTool.schema["function"]["name"] == SubmitTool.name

    @pytest.mark.parametrize(
        "answer",
        [
            "plain",
            "",
            "with 'single' quotes",
            'with "double" quotes',
            "with `backticks` and $variables and \\ backslashes",
            "multi\nline\nanswer",
            # Sentinel-as-substring: must not break since check is only on line[0].
            "preceded by COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT in body",
            "unicode 中文 αβγ 🚀",
        ],
    )
    def test_round_trip_through_local_environment(self, answer):
        """Build the submit command, run it in LocalEnvironment, and assert env raises
        Submitted with the exact answer preserved. This is the contract that makes the
        submit tool work end-to-end across any shell-quoting hazard."""
        command = SubmitTool().to_command({"answer": answer})
        env = LocalEnvironment()
        with pytest.raises(Submitted) as exc_info:
            env.execute({"command": command})
        assert exc_info.value.messages[0]["extra"]["submission"] == answer


def test_submit_to_command_uses_shell_safe_quoting():
    """Independent of round-tripping: the generated command must be safe to feed to a
    shell -- i.e. it must not let an answer escape into command position."""
    # An adversarial answer that, without quoting, would inject a second command.
    malicious = "x'; rm -rf / #"
    command = SubmitTool().to_command({"answer": malicious})
    # subprocess.run with shell=True will mimic what LocalEnvironment does.
    result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=5)
    # No injection: stdout is exactly sentinel + the literal answer text.
    assert result.returncode == 0
    assert result.stdout == f"COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n{malicious}"


# --- resolve_tools ----------------------------------------------------------


class TestResolveTools:
    def test_default_pair_resolves(self):
        tools = resolve_tools(["bash", "submit"])
        assert set(tools) == {"bash", "submit"}
        assert isinstance(tools["bash"], BashTool)
        assert isinstance(tools["submit"], SubmitTool)

    def test_single_tool_resolves(self):
        tools = resolve_tools(["bash"])
        assert set(tools) == {"bash"}

    def test_empty_list_raises(self):
        # Guards against silently passing tools=[] to the LLM, which providers
        # handle inconsistently (Anthropic errors, OpenAI quietly disables calls).
        with pytest.raises(ValueError, match="at least one tool"):
            resolve_tools([])

    def test_unknown_tool_raises_with_available_list(self):
        with pytest.raises(ValueError) as exc_info:
            resolve_tools(["bash", "no_such_tool"])
        assert "no_such_tool" in str(exc_info.value)
        # Error message should help the user pick a valid name.
        assert "bash" in str(exc_info.value)
        assert "submit" in str(exc_info.value)

    def test_returned_tools_satisfy_protocol(self):
        for tool in resolve_tools(["bash", "submit"]).values():
            assert isinstance(tool, Tool)


# --- BUILTIN extension contract --------------------------------------------


def test_builtin_registration_makes_custom_tool_resolvable():
    """User contract: registering a custom class in BUILTIN exposes it to
    resolve_tools (and therefore LitellmModelConfig.tools). Mirrors the pattern in
    mini-usage/extra_tools.py."""

    class _PingTool:
        name = "ping"
        schema = {
            "type": "function",
            "function": {
                "name": "ping",
                "description": "ping",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }

        def validate(self, args: dict) -> str | None:
            return None

        def to_command(self, args: dict) -> str:
            return "echo pong"

    BUILTIN["ping"] = _PingTool
    try:
        tools = resolve_tools(["ping"])
        assert isinstance(tools["ping"], _PingTool)
        assert tools["ping"].to_command({}) == "echo pong"
    finally:
        # Avoid leaking global state into other tests.
        BUILTIN.pop("ping", None)
