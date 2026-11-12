"""The free memory the jobs' line waits for, with the machine's real floor (the other tests set
it to nothing, conftest.memory_holds_nothing_back)."""

from types import SimpleNamespace

import pytest

from agent_app import jobs, settings, system


@pytest.fixture(autouse=True)
def memory_holds_nothing_back():
    """Overrides conftest's: this module reads the real floor."""


def test_a_16_gb_machine_with_4_gb_free_starts_answers_and_runs():
    # 2026-10-30 (the zip on a 16 GB Windows machine, 4.0 GB free): every answer and run waited
    # for 4.4 GB or more, the floor kept for the machine being 4 GB.
    defaults = {"image_slots": settings.ITEMS["image_slots"].default}
    assert jobs.memory_needed(jobs.workers_of("chat", defaults)) < 4000
    assert jobs.memory_needed(jobs.workers_of("run", defaults)) < 4000


def test_free_memory_on_windows_is_what_can_still_be_promised(monkeypatch):
    # 2026-11-02: with plenty of free memory but the commit room gone, the worker CLIs a run
    # started ended at once ("exit=1"); the line had looked at the free memory only.
    def status(ref):
        ref._obj.ullAvailPhys, ref._obj.ullAvailPageFile = 8000 << 20, 1500 << 20
        return 1

    windll = SimpleNamespace(kernel32=SimpleNamespace(GlobalMemoryStatusEx=status))
    monkeypatch.setattr(system, "WINDOWS", True)
    monkeypatch.setattr(system.ctypes, "windll", windll, raising=False)
    assert system.free_mb() == 1500
