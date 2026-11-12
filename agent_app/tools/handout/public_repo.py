"""Put the app at HEAD into the public repository's folder (user 2026-11-06: going public should be
switching the repository, nothing more): agent_app/ replaced whole, without this repository's
history, and the lockfile and lint settings its package.json goes with. Its screen goes built
(agent_app/ui/dist), and start.cmd and start.sh at its top (user 2026-11-11: a clone runs with
Git alone, no Node.js; the public repository has no zip). That repository's README, LICENSE,
package.json, .gitignore and samples are its own. Nothing is committed or sent there: look,
commit and push there.

npm run public-repo
"""

import json
import shutil
import socket
import subprocess
from pathlib import Path

from build import HERE, REPO, source_holding

SENT = ["agent_app", "vite.config.ts", "package-lock.json"]


def git(*argv, cwd=REPO):
    return subprocess.run(
        ["git", *argv], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def main():
    public = json.loads((HERE / "handout.json").read_text(encoding="utf-8"))["public"]
    folder = Path(public["repo"]).expanduser()
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
    git("rm", "-rqf", "--ignore-unmatch", "agent_app", cwd=folder)
    archive = subprocess.run(
        ["git", "archive", "HEAD", "agent_app", "vite.config.ts"],
        cwd=REPO,
        capture_output=True,
        check=True,
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(folder)], input=archive, check=True)
    shutil.copytree(dist, folder / "agent_app/ui/dist")
    for start in ("start.cmd", "start.sh"):
        shutil.copy2(folder / "agent_app/tools/handout/files" / start, folder / start)
    lock = json.loads(git("show", "HEAD:package-lock.json"))
    lock["name"] = lock["packages"][""]["name"] = public["name"]
    (folder / "package-lock.json").write_text(
        json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        git("status", "--short", "--", ".", cwd=folder).count("\n"),
        "files changed in",
        folder,
    )


if __name__ == "__main__":
    main()
