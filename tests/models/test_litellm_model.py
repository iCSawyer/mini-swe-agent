from unittest.mock import MagicMock, patch

import pytest

from minisweagent.exceptions import FormatError
from minisweagent.models.litellm_model import LitellmModel, LitellmModelConfig
from minisweagent.models.utils.actions_toolcall import BASH_TOOL
from minisweagent.models.utils.tools import BUILTIN, BashTool, SubmitTool


class TestLitellmModelConfig:
    def test_default_format_error_template(self):
        assert LitellmModelConfig(model_name="test").format_error_template == "{{ error }}"

    def test_default_tools_are_bash_and_submit(self):
        assert LitellmModelConfig(model_name="test").tools == ["bash", "submit"]

    def test_custom_tools_list_is_respected(self):
        assert LitellmModelConfig(model_name="test", tools=["bash"]).tools == ["bash"]

    def test_unknown_tool_in_config_raises_at_init(self):
        # resolve_tools runs in LitellmModel.__init__, so a typo'd tool name must
        # fail fast at construction, not silently degrade at query time.
        with pytest.raises(ValueError, match="Unknown tool"):
            LitellmModel(model_name="test", tools=["bash", "no_such_tool"])

    def test_empty_tools_list_raises_at_init(self):
        with pytest.raises(ValueError, match="at least one tool"):
            LitellmModel(model_name="test", tools=[])


def _mock_litellm_response(tool_calls):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.tool_calls = tool_calls
    mock_response.choices[0].message.model_dump.return_value = {"role": "assistant", "content": None}
    mock_response.model_dump.return_value = {}
    return mock_response


class TestLitellmModel:
    @patch("minisweagent.models.litellm_model.litellm.completion")
    @patch("minisweagent.models.litellm_model.litellm.cost_calculator.completion_cost")
    def test_query_includes_default_tools(self, mock_cost, mock_completion):
        tool_call = MagicMock()
        tool_call.function.name = "bash"
        tool_call.function.arguments = '{"command": "echo test"}'
        tool_call.id = "call_1"
        mock_completion.return_value = _mock_litellm_response([tool_call])
        mock_cost.return_value = 0.001

        model = LitellmModel(model_name="gpt-4")
        model.query([{"role": "user", "content": "test"}])

        mock_completion.assert_called_once()
        assert mock_completion.call_args.kwargs["tools"] == [BASH_TOOL, SubmitTool.schema]

    @patch("minisweagent.models.litellm_model.litellm.completion")
    @patch("minisweagent.models.litellm_model.litellm.cost_calculator.completion_cost")
    def test_parse_actions_valid_tool_call(self, mock_cost, mock_completion):
        tool_call = MagicMock()
        tool_call.function.name = "bash"
        tool_call.function.arguments = '{"command": "ls -la"}'
        tool_call.id = "call_abc"
        mock_completion.return_value = _mock_litellm_response([tool_call])
        mock_cost.return_value = 0.001

        model = LitellmModel(model_name="gpt-4")
        result = model.query([{"role": "user", "content": "list files"}])
        assert result["extra"]["actions"] == [{"command": "ls -la", "tool_call_id": "call_abc", "tool_name": "bash"}]

    @patch("minisweagent.models.litellm_model.litellm.completion")
    @patch("minisweagent.models.litellm_model.litellm.cost_calculator.completion_cost")
    def test_parse_actions_no_tool_calls_raises(self, mock_cost, mock_completion):
        mock_completion.return_value = _mock_litellm_response(None)
        mock_cost.return_value = 0.001

        model = LitellmModel(model_name="gpt-4")
        with pytest.raises(FormatError):
            model.query([{"role": "user", "content": "test"}])

    def test_format_observation_messages(self):
        model = LitellmModel(model_name="gpt-4", observation_template="{{ output.output }}")
        message = {"extra": {"actions": [{"command": "echo test", "tool_call_id": "call_1"}]}}
        outputs = [{"output": "test output", "returncode": 0}]
        result = model.format_observation_messages(message, outputs)
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call_1"
        assert result[0]["content"] == "test output"

    def test_format_observation_messages_no_actions(self):
        model = LitellmModel(model_name="gpt-4")
        result = model.format_observation_messages({"extra": {}}, [])
        assert result == []

    @patch("minisweagent.models.litellm_model.litellm.completion")
    @patch("minisweagent.models.litellm_model.litellm.cost_calculator.completion_cost")
    def test_query_with_bash_only_omits_submit_schema(self, mock_cost, mock_completion):
        # tools=["bash"] is the recommended config for SWE-bench (avoids the prompt vs.
        # submit-tool conflict flagged in the original review).
        tool_call = MagicMock()
        tool_call.function.name = "bash"
        tool_call.function.arguments = '{"command": "echo test"}'
        tool_call.id = "call_1"
        mock_completion.return_value = _mock_litellm_response([tool_call])
        mock_cost.return_value = 0.001

        model = LitellmModel(model_name="gpt-4", tools=["bash"])
        model.query([{"role": "user", "content": "test"}])

        passed_tools = mock_completion.call_args.kwargs["tools"]
        assert passed_tools == [BashTool.schema]
        assert SubmitTool.schema not in passed_tools

    @patch("minisweagent.models.litellm_model.litellm.completion")
    @patch("minisweagent.models.litellm_model.litellm.cost_calculator.completion_cost")
    def test_custom_tool_registered_in_builtin_flows_through_to_action(self, mock_cost, mock_completion):
        # End-to-end of the user-facing extension contract: register a tool in BUILTIN,
        # configure it on the model, the model calls it, and the produced action carries
        # the right command + tool_name.

        class _StubTool:
            name = "stub"
            schema = {
                "type": "function",
                "function": {
                    "name": "stub",
                    "description": "stub",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            }

            def validate(self, args: dict) -> str | None:
                return None

            def to_command(self, args: dict) -> str:
                return "echo stubbed"

        BUILTIN["stub"] = _StubTool
        try:
            tool_call = MagicMock()
            tool_call.function.name = "stub"
            tool_call.function.arguments = "{}"
            tool_call.id = "call_stub"
            mock_completion.return_value = _mock_litellm_response([tool_call])
            mock_cost.return_value = 0.001

            model = LitellmModel(model_name="gpt-4", tools=["stub"])
            result = model.query([{"role": "user", "content": "use stub"}])

            assert mock_completion.call_args.kwargs["tools"] == [_StubTool.schema]
            assert result["extra"]["actions"] == [
                {"command": "echo stubbed", "tool_call_id": "call_stub", "tool_name": "stub"}
            ]
        finally:
            BUILTIN.pop("stub", None)
