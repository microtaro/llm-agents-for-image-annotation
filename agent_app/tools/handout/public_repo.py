"""Put the app at HEAD into the public repository's folder (user 2026-11-06: going public should be
switching the repository, nothing more): agent_app/ replaced whole, without this repository's
history, and the lockfile and lint settings its package.json goes with. Its screen goes built
(agent_app/ui/dist), and start.cmd and start.sh at its top (user 2026-11-11: a clone runs with
Git alone, no Node.js). The public repository is the one way the app is given (user 2026-11-17:
no zip, in the company too). That repository's README, LICENSE, package.json, .gitignore and
samples are its own. Nothing is committed or sent there: look, commit and push there.

npm run public-repo
"""

import json
import shutil
import socket
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
# The public repository: its name (its package.json's and lockfile's) and its clone here.
NAME = "llm-agents-for-image-annotation"
FOLDER = Path.home() / "ai_project" / NAME
SENT = ["agent_app", "vite.config.ts", "package-lock.json"]


def git(*argv, cwd=REPO):
    return subprocess.run(
        ["git", *argv], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def source_holding(word):
    """The app's committed files that hold the word: its folder goes public whole, tools and all
    (2026-11-06: tools/ui_audit's requests named this machine's account, and nothing looked
    there)."""
    found = subprocess.run(
        ["git", "grep", "-il", "-e", word, "--", "agent_app"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,  # git grep answers 1 when nothing holds it
    )
    return found.stdout.splitlines()


def main():
    if changed := git("status", "--porcelain", "--", *SENT).strip():
        raise SystemExit(f"コミットしてから流してください:\n{changed}")
    words = (
        Path.home().name,
        socket.gethostname(),
        git("config", "user.name").strip(),
    )
    for word in words:
        if found := source_holding(word):
            raise SystemExit(f"公開しない名前「{word}」がコードに残っています: {found}")
    # The screen built from the code at HEAD (agent_app is as committed, above).
    subprocess.run(["npm", "run", "--silent", "build:agent-ui"], cwd=REPO, check=True)
    dist = REPO / "agent_app/ui/dist"
    for path in dist.rglob("*"):
        if path.is_file():
            text = path.read_bytes().lower()
            for word in words:
                if word.lower().encode() in text:
                    raise SystemExit(
                        f"公開しない名前「{word}」が作った画面に残っています: {path}"
                    )
    # Only what that repository tracks goes: a database or log of a run there stays.
    git("rm", "-rqf", "--ignore-unmatch", "agent_app", cwd=FOLDER)
    archive = subprocess.run(
        ["git", "archive", "HEAD", "agent_app", "vite.config.ts"],
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(FOLDER)], input=archive, check=True)
    shutil.copytree(dist, FOLDER / "agent_app/ui/dist")
    for start in ("start.cmd", "start.sh"):
        shutil.copy2(FOLDER / "agent_app/tools/handout/files" / start, FOLDER / start)
    lock = json.loads(git("show", "HEAD:package-lock.json"))
    lock["name"] = lock["packages"][""]["name"] = NAME
    (FOLDER / "package-lock.json").write_text(
        json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        git("status", "--short", "--", ".", cwd=FOLDER).count("\n"),
        "files changed in",
        FOLDER,
    )
    # Changes not in a version yet go under the next version's heading when it is released
    # (user 2026-11-18): said here, as this runs before every release.
    for name in ("CHANGELOG.md", "CHANGELOG.ja.md"):
        path = FOLDER / name
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if "\n## Unreleased" in text or "\n## 未リリース" in text:
            print(
                f"{name} に未リリースの節があります。版を出す時は、"
                "見出しを版の番号と日付に替えてください。"
            )


if __name__ == "__main__":
    main()
