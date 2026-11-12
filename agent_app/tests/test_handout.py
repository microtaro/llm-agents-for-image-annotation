"""The zip given to people (tools/handout/build.py)."""

import importlib.util
import sqlite3
import subprocess
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "handout_build",
    Path(__file__).resolve().parents[1] / "tools/handout/build.py",
)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def test_the_zip_says_nothing_of_the_machine_that_made_it(tmp_path):
    # 2026-11-05: the library's tooltip showed /home/<user>/.../export/... by image_sources, the
    # decisions that made the datasets held the same folder, and the libraries' bin scripts began
    # with this machine's Python.
    path = tmp_path / "agent.db"
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE dataset_images(source_path TEXT);
        CREATE TABLE image_sources(path TEXT);
        CREATE TABLE decisions(content_json TEXT);
        INSERT INTO dataset_images VALUES('/home/someone/build/export/a/1.png');
        INSERT INTO image_sources VALUES('/home/someone/build/export/a/1.png');
        INSERT INTO decisions VALUES('{"path": "/home/someone/build/export/a"}');
        INSERT INTO decisions VALUES('{"path": "/home/someone/build/export"}');
        """
    )
    db.commit()
    assert build.files_holding(tmp_path, "someone") == ["agent.db"]
    build.forget_the_machine(db, "/home/someone/build/export")
    assert db.execute("SELECT source_path FROM dataset_images").fetchall() == [(None,)]
    assert db.execute("SELECT count(*) FROM image_sources").fetchone() == (0,)
    assert db.execute("SELECT content_json FROM decisions").fetchall() == [
        ('{"path": "a"}',),
        ('{"path": ""}',),
    ]
    db.close()
    (tmp_path / "mcp").write_text("#!/home/someone/.venv/bin/python\n")
    assert build.files_holding(tmp_path, "someone") == ["mcp"]


def test_the_public_zip_looks_at_the_apps_whole_folder(tmp_path, monkeypatch):
    # 2026-11-06: tools/ui_audit's requests held the account's name; they are not in the zip, so
    # the zip's own check passed, and the folder goes public with it.
    monkeypatch.setattr(build, "REPO", tmp_path)
    request = tmp_path / "agent_app/tools/request.md"
    request.parent.mkdir(parents=True)
    request.write_text("/home/Someone/annotation\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    assert build.source_holding("someone") == ["agent_app/tools/request.md"]
    assert build.source_holding("nobody") == []
