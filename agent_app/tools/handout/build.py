"""Make the zip given to someone to try the app (user 2026-10-28: not published; unzip and
start; docs/2026-10-19-public-release-plan.md "人に渡す zip"). Each new version is a new zip, and
the person deletes the old folder whole: the data is not carried over.

The zip holds the app at HEAD (git archive: commit first), its screen built, a database of the
datasets chosen in handout.json (written out of the work's own server, 3110, in this app's form
and taken in again, so their records come too; and empty ones made of a dataset's images, no
plan), start for Windows (Annotation.exe, made from launcher.c; Windows' Python and the locked
libraries are in the zip, python-windows, nothing fetched) and Mac/Linux (.sh; the first start
installs), README.md and the LICENSE. Its server listens on config.PORT_GIVEN or the next free port (no
.claude/project.config.json inside).

The one way to make it (user 2026-10-29: "made from the work's own app by a fixed way"):
commit, keep npm run dev up, then npm run zip. The last zip moves to out/old. With --public, the
datasets are handout.json's samples, written out in this app's form, so the server need not be up.
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from agent_app.config import VERSION

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WORK = "http://127.0.0.1:3110"
# The server that makes the zip's database, apart from the work's (3110), the copy's (4110) and
# the zip's own (3900 and up).
BUILDING = 4900
CODE = [
    "agent_app/agent_app",
    "agent_app/pyproject.toml",
    "agent_app/uv.lock",
    "agent_app/.python-version",
    # The screen's dictionary: the server names the settings by it (screen_words.dictionary).
    "agent_app/ui/src/i18n/ja.json",
    "agent_app/ui/src/i18n/en.json",
]
# The uv the zip's start.sh puts in on Mac and Linux (files/start.sh names the same).
ZIP_UV = "0.13.6"
# The zig that makes Annotation.exe for Windows here (a C compiler for other systems, from PyPI).
ZIG = "0.16.0"
# The person's clock, for the old zips' names (times said to the user are JST).
JST = timezone(timedelta(hours=9))
STORED = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".zip"}


def run(*argv, cwd=REPO):
    subprocess.run(argv, cwd=cwd, check=True)


def fetch(url, path):
    """A download into path, as it streams in."""
    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as r:
        r.raise_for_status()
        with path.open("wb") as out:
            for chunk in r.iter_bytes():
                out.write(chunk)


def committed():
    """A change not committed stops it (the zip is a commit's), before the last zip is moved."""
    changed = subprocess.run(
        ["git", "status", "--porcelain", "--", *CODE, "agent_app/ui"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if changed.strip():
        raise SystemExit(
            f"コミットしてから流してください。コミットしていない変更:\n{changed}"
        )


def code_to(folder):
    """The app's code at HEAD and its screen built."""
    archive = subprocess.run(
        ["git", "archive", "HEAD", *CODE], cwd=REPO, capture_output=True, check=True
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(folder)], input=archive, check=True)
    run("npm", "run", "build:agent-ui")
    shutil.copytree(REPO / "agent_app/ui/dist", folder / "agent_app/ui/dist")


def work_is_up():
    """The work's own server, whose datasets go in the zip, answers (else say how to start it)."""
    try:
        httpx.get(f"{WORK}/health", timeout=3).raise_for_status()
    except httpx.HTTPError:
        raise SystemExit(
            "開発のサーバー（3110）が動いていません。npm run dev で起こしてから、もう一度流してください。"
        ) from None


def written_out(numbers, dest):
    """The datasets of the work's server written out in this app's form: {number: folder}."""
    with httpx.Client(base_url=WORK, timeout=600) as work:
        listed = work.get("/v1/datasets").json()["datasets"]
        by_number = {d["number"]: d for d in listed}
        missing = [n for n in numbers if n not in by_number]
        if missing:
            raise SystemExit(f"No such dataset: {missing}")
        response = work.post(
            "/v1/library/export",
            json={
                "dataset_ids": [by_number[n]["id"] for n in numbers],
                "dest": str(dest),
                "format": "app",
            },
        )
        response.raise_for_status()
    written = {w["dataset_id"]: Path(w["path"]) for w in response.json()["written"]}
    return {n: written[by_number[n]["id"]] for n in numbers}


def forget_the_machine(db, *folders):
    """The folders the images came from are this machine's (2026-10-29: the zip's library showed
    a folder of the build's own; 2026-11-05: still, by image_sources, and in the decisions that
    made the datasets, with the user's name): the person's say none."""
    with db:
        db.execute("UPDATE dataset_images SET source_path=NULL")
        db.execute("DELETE FROM image_sources")
        for folder in folders:
            for place in (f"{folder}/", str(folder)):
                db.execute(
                    "UPDATE decisions SET content_json=replace(content_json, ?, '')",
                    (place,),
                )
    # What was taken out would stay in the file's free pages.
    db.execute("VACUUM")


def files_holding(folder, word):
    """The files of the folder that hold the word, for what must not go (2026-11-05: the zip said
    the user's name in its database and at the head of the libraries' bin scripts)."""
    needle = word.encode()
    return [
        str(path.relative_to(folder))
        for path in sorted(folder.rglob("*"))
        if path.is_file() and needle in path.read_bytes()
    ]


def source_holding(word):
    """The app's committed files that hold the word: its folder goes public with the zip, tools
    and all (2026-11-06: tools/ui_audit's requests named this machine's account, and nothing
    looked there, as they are not in the zip)."""
    found = subprocess.run(
        ["git", "grep", "-il", "-e", word, "--", "agent_app"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,  # git grep answers 1 when nothing holds it
    )
    return found.stdout.splitlines()


def database(db_path, exported, folders, empties, places):
    """The zip's database: the datasets taken in, the empty ones made. places: the folders of
    this machine they were read from."""
    server = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sys, uvicorn; from agent_app.app import create_app;"
                " uvicorn.run(create_app(sys.argv[1]), host='127.0.0.1',"
                f" port={BUILDING}, log_level='warning')"
            ),
            str(db_path),
        ]
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{BUILDING}", timeout=600) as app:
            for _ in range(100):
                try:
                    app.get("/health").raise_for_status()
                    break
                except httpx.HTTPError:
                    time.sleep(0.2)
            if any(exported.iterdir()):
                taken = app.post("/v1/library/import", json={"path": str(exported)})
                taken.raise_for_status()
            for number, name, purpose in empties:
                folder = folders[number]
                document = json.loads(
                    (folder / "dataset.json").read_text(encoding="utf-8")
                )
                made = app.post(
                    "/v1/datasets",
                    json={
                        "name": name,
                        "purpose": purpose,
                        "paths": [str(folder / i["file"]) for i in document["images"]],
                    },
                )
                made.raise_for_status()
            return app.get("/v1/datasets").json()["datasets"]
    finally:
        server.terminate()
        server.wait(timeout=30)
        # Closed here, not when collected (2026-10-29: a connection closed later took its
        # -shm file away while the folder was being zipped).
        db = sqlite3.connect(db_path)
        try:
            forget_the_machine(db, *places)
            # Back into the one file: the last connection closed ends the write-ahead log.
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            db.close()


def readme(datasets):
    ja, en = [], []
    for d in sorted(datasets, key=lambda d: d["number"]):
        version = d["latest_revision"]
        purpose = d["purpose"].rstrip(".。")
        plan_ja = (
            f"計画書 第{version}版"
            if version
            else "何もしていない（計画もアノテーションも無い）"
        )
        plan_en = (
            f"plan version {version}"
            if version
            else "nothing done yet (no plan, no annotations)"
        )
        ja.append(
            f"- #{d['number']} {d['name']}（{d['image_count']}枚）— {purpose}。{plan_ja}"
        )
        en.append(
            f"- #{d['number']} {d['name']} ({d['image_count']} images): {purpose}. {plan_en.capitalize()}."
        )
    text = (HERE / "files/README.md").read_text(encoding="utf-8")
    return (
        text.replace("{version}", VERSION)
        .replace("{datasets_en}", "\n".join(en))
        .replace("{datasets}", "\n".join(ja))
    )


def windows_python(folder):
    """Windows' Python and every locked library, in the folder's python-windows (user
    2026-10-30: give it with the libraries in; a machine whose antivirus looks into HTTPS
    stopped uv's downloads, "UnknownIssuer"): python-build-standalone's x64 build of the
    version agent_app/.python-version names (it runs on ARM Windows too), the licences of what
    it holds besides Python (licenses/), the lock's libraries for it in its site-packages (their
    hashes checked), and a .pth putting the app's folder on its path, relative so the folder can
    move."""
    uv = os.environ.get("UV", "uv")
    version = (REPO / "agent_app/.python-version").read_text(encoding="utf-8").strip()
    # The build of it that start.sh's uv chooses on Mac and Linux, and the zips before chose on
    # Windows (2026-10-30: this machine's older uv chose an older build, without Tk's library
    # folder, and the small window's mark in the taskbar looked different).
    listed = subprocess.run(
        [uv, "tool", "run", "--from", f"uv=={ZIP_UV}", "uv", "python", "list"]
        + ["--all-platforms", "--only-downloads", "--output-format", "json"]
        + [f"cpython-{version}-windows-x86_64-none"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    (found,) = json.loads(listed)
    target = folder / "python-windows"
    site = target / "Lib/site-packages"
    with tempfile.TemporaryDirectory() as temp:
        archive = Path(temp) / "python.tar.gz"
        fetch(found["url"], archive)
        with tarfile.open(archive) as tar:
            tar.extractall(temp, filter="data")
        shutil.move(Path(temp) / "python", target)
        # The licences of what this build holds besides Python, in python-windows/licenses
        # (2026-11-11: its LICENSE.txt names only Python's own, bzip2's and zstd's, not OpenSSL's,
        # libffi's, SQLite's, Tcl/Tk's or xz's): only the same build's full archive has them.
        full_url = found["url"].replace(
            "-install_only_stripped.tar.gz", "-pgo-full.tar.zst"
        )
        if full_url == found["url"]:
            raise SystemExit(
                f"No full archive of this Python to take its licences from: {full_url}"
            )
        full = Path(temp) / "full.tar.zst"
        fetch(full_url, full)
        with tarfile.open(full, "r:zst") as tar:
            licences = [
                m
                for m in tar.getmembers()
                if m.isfile() and m.name.startswith("python/licenses/")
            ]
            if not licences:
                raise SystemExit(f"No licences in {full_url}")
            tar.extractall(Path(temp) / "full", members=licences, filter="data")
        shutil.move(Path(temp) / "full/python/licenses", target / "licenses")
        locked = Path(temp) / "requirements.txt"
        run(
            uv,
            "export",
            "--project",
            "agent_app",
            "--frozen",
            "--no-dev",
            "--no-emit-project",
            "--format",
            "requirements-txt",
            "--quiet",
            "-o",
            str(locked),
        )
        run(
            uv,
            "pip",
            "install",
            "--quiet",
            "--target",
            str(site),
            "--python-platform",
            "x86_64-pc-windows-msvc",
            "--python-version",
            version,
            "--require-hashes",
            "-r",
            str(locked),
        )
    (site / "agent_app.pth").write_text("../../../agent_app\n", encoding="utf-8")
    # Commands nothing runs, each beginning with the path of this machine's Python.
    shutil.rmtree(site / "bin")


def windows_start(folder):
    """Annotation.exe, the start on Windows: launcher.c with the app's mark (launcher.rc), a
    program with no console (user 2026-10-30: start.cmd opened a terminal)."""
    uv = os.environ.get("UV", "uv")
    run(
        uv,
        "run",
        "--no-project",
        "--with",
        f"ziglang=={ZIG}",
        "--",
        "python",
        "-m",
        "ziglang",
        "cc",
        "-target",
        "x86_64-windows-gnu",
        "-Os",
        "-s",
        "-Wl,--subsystem,windows",
        "-o",
        str(folder / "Annotation.exe"),
        str(HERE / "launcher.c"),
        str(HERE / "launcher.rc"),
    )


def zipped(folder, zip_path):
    with zipfile.ZipFile(zip_path, "w") as z:
        for path in sorted(folder.rglob("*")):
            if path.is_dir():
                continue
            name = f"{folder.name}/{path.relative_to(folder).as_posix()}"
            info = zipfile.ZipInfo.from_file(path, name)
            info.compress_type = (
                zipfile.ZIP_STORED
                if path.suffix.lower() in STORED
                else zipfile.ZIP_DEFLATED
            )
            if path.suffix == ".sh":
                info.external_attr = 0o100755 << 16
            with path.open("rb") as source:
                z.writestr(info, source.read())


def main():
    chosen = json.loads((HERE / "handout.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(
        description="Make the zip of handout.json's choice."
    )
    parser.add_argument(
        "--out", default=chosen["out"], help="Instead of handout.json's."
    )
    parser.add_argument(
        "--min",
        action="store_true",
        help="The light one: handout.json's min, named agent-app-<version>-min.",
    )
    parser.add_argument(
        "--public",
        action="store_true",
        help="The one to publish: handout.json's public, named <name>-<version>.",
    )
    args = parser.parse_args()
    out = Path(args.out).expanduser()
    public = chosen["public"] if args.public else None
    if args.min:
        chosen = chosen["min"]
    numbers = [] if public else list(chosen["datasets"])
    empties = (
        []
        if public
        else [(e["from"], e["name"], e["purpose"]) for e in chosen["empty"]]
    )
    out.mkdir(parents=True, exist_ok=True)
    folder = out / (
        f"{public['name']}-{VERSION}"
        if public
        else f"agent-app-{VERSION}{'-min' if args.min else ''}"
    )
    zip_path = out / f"{folder.name}.zip"
    samples = Path(public["samples"]).expanduser() if public else None
    # The checks first: a run stopped by one leaves the last zip as it was.
    committed()
    if samples is None:
        work_is_up()
    elif not samples.is_dir():
        raise SystemExit(f"見本のフォルダがありません: {samples}")
    elif found := source_holding(Path.home().name):
        raise SystemExit(f"この PC のユーザー名がコードに残っています: {found}")
    # The last one made: its folder is this tool's own, its zip is kept in old/.
    if folder.exists():
        shutil.rmtree(folder)
    if zip_path.exists():
        (out / "old").mkdir(exist_ok=True)
        stamp = datetime.fromtimestamp(zip_path.stat().st_mtime, JST).strftime(
            "%Y%m%d-%H%M"
        )
        zip_path.rename(out / "old" / f"{folder.name}-{stamp}.zip")
    folder.mkdir()
    code_to(folder)
    with tempfile.TemporaryDirectory(dir=out) as temp:
        exported, images_only = samples or Path(temp) / "export", Path(temp) / "images"
        exported.mkdir(exist_ok=True)
        images_only.mkdir()
        folders = written_out(numbers, exported) if numbers else {}
        # An empty one of a dataset not given: only its images are wanted, apart from the
        # folders taken in.
        others = sorted({n for n, _, _ in empties} - set(numbers))
        if others:
            folders |= written_out(others, images_only)
        datasets = database(
            folder / "agent_app/agent.db",
            exported,
            folders,
            empties,
            [exported, images_only],
        )
    windows_python(folder)
    windows_start(folder)
    (folder / "README.md").write_text(readme(datasets), encoding="utf-8")
    shutil.copy(HERE / "files/start.sh", folder / "start.sh")
    (folder / "start.sh").chmod(0o755)
    shutil.copy(HERE / "files/LICENSE", folder / "LICENSE")
    found = files_holding(folder, Path.home().name)
    if found:
        raise SystemExit(f"この PC のユーザー名が残っています: {found}")
    zipped(folder, zip_path)
    print(
        f"{zip_path}（{zip_path.stat().st_size / 1e6:.0f} MB、データセット {len(datasets)}）"
    )


if __name__ == "__main__":
    main()
