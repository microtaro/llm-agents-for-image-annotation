from agent_app.claude_execution import ClaudeStream


def test_a_tool_called_by_a_name_outside_the_apps_goes_on_as_a_failed_call(tmp_path):
    # 2026-10-29: the model called "look" without its prefix; the answer stopped there with
    # "Claude returned an unexpected tool: look", though the CLI refuses it and the model
    # calls again.
    stream = ClaudeStream(tmp_path, "claude-opus-5-5")
    started = stream.events(
        {
            "type": "assistant",
            "uuid": "u1",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "look", "input": {}}
                ]
            },
        }
    )
    assert [e["item"]["tool"] for e in started] == ["look"]
    ended = stream.events(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "is_error": True,
                        "content": "No such tool available: look",
                    }
                ]
            },
        }
    )
    assert ended[0]["item"]["status"] == "failed"
