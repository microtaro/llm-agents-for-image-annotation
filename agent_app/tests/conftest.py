import pytest
from agent_app.app import create_app
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture(autouse=True)
def no_real_worker_cli(monkeypatch):
    """A test never starts a real worker CLI (2026-10-20: a side question's test started a
    real Claude, passing without waiting for it). test_residents.py puts its fake CLIs in."""
    from agent_app import residents

    def refused(*args, **kwargs):
        raise AssertionError("A test started a real worker CLI; fake the turn instead")

    monkeypatch.setattr(residents, "claude_argv", refused)
    monkeypatch.setattr(residents, "codex_executable", refused)


@pytest.fixture(autouse=True)
def memory_holds_nothing_back(monkeypatch):
    """The machine's free memory does not hold a test's jobs back (2026-10-28: on Windows, with
    the app and CLIs running, the tests' runs waited for memory and did not end in time). A test
    of the memory's hold sets its own floor."""
    from agent_app import jobs

    monkeypatch.setattr(jobs, "FLOOR_MB", 0)
    monkeypatch.setattr(jobs, "WORKER_MB", 0)


@pytest.fixture
def client(tmp_path):
    with TestClient(
        create_app(tmp_path / "test.db"), base_url="http://127.0.0.1"
    ) as test_client:
        yield test_client


@pytest.fixture
def image_file(tmp_path):
    """A small PNG on disk; call with a color to get different bytes."""

    def make(color=(200, 30, 30), name="a.png", folder=None):
        target = (folder or tmp_path) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (40, 30), color).save(target)
        return target

    return make
