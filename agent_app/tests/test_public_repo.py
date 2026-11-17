"""What goes to the public repository (tools/handout/public_repo.py)."""

import importlib.util
import subprocess
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "public_repo",
    Path(__file__).resolve().parents[1] / "tools/handout/public_repo.py",
)
public_repo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public_repo)


def test_the_public_repository_looks_at_the_apps_whole_folder(tmp_path, monkeypatch):
    # 2026-11-06: tools/ui_audit's requests held the account's name; nothing looked there, and
    # the folder goes public whole.
    monkeypatch.setattr(public_repo, "REPO", tmp_path)
    request = tmp_path / "agent_app/tools/request.md"
    request.parent.mkdir(parents=True)
    request.write_text("/home/Someone/annotation\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    assert public_repo.source_holding("someone") == ["agent_app/tools/request.md"]
    assert public_repo.source_holding("nobody") == []
