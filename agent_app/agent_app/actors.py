"""Who did a thing (definition 21.2): one word in every column that says who, from one place.
person (the person, on the screen), agent:<worker> (a worker of a dataset), server (what the
server writes by itself: a withdrawal, a migration, a run stopped at a start) and outside (the
outer MCP and HTTP with no worker's mark: the development tools). The worker AI of a run decides
nothing, so it is not one: what it made is its run's.
"""

from .errors import ApiError

PERSON = "person"
SERVER = "server"
OUTSIDE = "outside"


def agent(key):
    return f"agent:{key}"


def is_agent(who):
    """Whether a worker did it (else a person, the server or the outside, who decide)."""
    return who.startswith("agent:")


def who_of(request):
    """Who calls: the worker the server bound in the headers (its CLI gets them), else the
    person when the screen says so (X-Actor: ui), else the outside."""
    from .agents import AGENTS

    key = request.headers.get("x-annotation-agent")
    if key is not None:
        if key not in AGENTS:
            raise ApiError(403, "agent_scope", "No such worker")
        return agent(key)
    return PERSON if request.headers.get("x-actor") == "ui" else OUTSIDE


def as_read_by(who, reader):
    """Who did it, as the worker reader reads it (definition 68.1): you (the reader itself),
    another worker by its name, or person, server, outside."""
    return "you" if who == agent(reader) else who.removeprefix("agent:")


def headers_of(who):
    """The headers an inner call is made with to act as who (a box applied by the person)."""
    return {"X-Actor": "ui"} if who == PERSON else {}
