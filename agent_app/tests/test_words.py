"""The workers' rules say the screen's words and what a show may say from one place each
(issue #3 U-14: the list was copied into every prompt, and the copies differed: one still named
a box state the server no longer has)."""

from agent_app.object_types import ProposalWhere, show_words
from agent_app.screen_words import words

from agent_app import agent_answer, library_here


def test_every_prompt_says_the_one_list():
    for prompt in (agent_answer.RULES, library_here.RULES):
        assert words() in prompt
    assert show_words() in agent_answer.RULES
    states = ProposalWhere.model_fields["state"].annotation
    assert (
        "stale" not in str(states) and "stale" not in show_words().split("proposal:")[1]
    )
