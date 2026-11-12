"""Have a Codex model check the screens as a person would (DESIGN.md "見た目の一貫性" and
"一方向か双方向か"; docs/ops/ui-audit.md). Three checks, each a request in this folder:

- links.md: a state shown in two places changes from either side; operations only one
  screen has, and the scenes that want them elsewhere.
- visual.md: the same kind of information and operation in the same place, shape, words and
  color on every screen.
- flow.md: what a person's own operations show, against the map, its steps, the next step
  and the library card (user 2026-10-07). It saves and runs a little, so only on a copy.
- time.md: ten pieces of work from making a dataset to annotating with AI, by the talk and by
  the screens, the waits timed (user 2026-10-26: where the time goes). Saves and runs; on a copy.
- time2.md: five other pieces of work, timed the same way (fixing the plan after a trial, a
  reference, stopping a run, asking the reception first, the training set and the turns).
- chat.md: scenarios of docs/2026-10-28-chat-test-scenarios.md, chosen by their ids, done from
  the start by the talk, what each change of state shows recorded (user 2026-10-28: forty
  scenarios, varied, of continuous work). Several run at once, each named (--name). On a copy.

The model drives the debug Chrome through chrome-devtools MCP and only reports. links and
visual change nothing kept (no runs, no saves); flow saves and runs twice at most, on the
copy of snapshot.py only. When the model is busy, the same session is resumed.

uv run --project agent_app python agent_app/tools/ui_audit/run.py links \\
  --datasets "「Astra 薬の箱」「Astra レイアウト」"
"""

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RESUME = (
    "止まったので続きから再開してください。まだ調べていない所を最初の頼みどおりに調べ、"
    "最後に頼みの形で全体を報告してください。ページの番号は list_pages で確かめてから。"
)
# Said with every check (found 2026-10-27): chrome-devtools' fill sets a text of 100 characters
# or more as the field's value at once instead of typing it, the screen (React) does not take
# it as typed, and its send button stayed off.
TYPING = (
    "\n\n## 文の入れ方\n\n入力欄に文を入れる時は、入力欄を押してから type_text で打ちます。"
    "fill は100文字以上の文を打たずに一度に入れるので、画面が入力に気づかず「送る」などが"
    "押せないままになります。fill は短い値と選択肢にだけ使います。\n"
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "check",
        choices=[
            "links",
            "visual",
            "flow",
            "time",
            "time2",
            "chat",
        ],
    )
    parser.add_argument(
        "--datasets", required=True, help="The datasets it may touch, in words."
    )
    # GPT-6.1-Sol at xhigh (user 2026-10-08: Codex use is growing; same effort, Sol).
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--effort", default="xhigh")
    parser.add_argument("--tries", type=int, default=8)
    # The app to check: the work's own server, or a copy at one commit (snapshot.py, 4110),
    # so the checks run apart from the work (user 2026-10-07).
    parser.add_argument("--app-url", default=None)
    # Codex's faster service tier, e.g. "priority" (the app's run models list it as a speed).
    parser.add_argument("--tier", default=None)
    # chat: the scenarios' ids, and a name for this group (its tab and its files apart from the
    # other groups run at the same time).
    parser.add_argument("--scenarios", default="")
    parser.add_argument("--name", default="")
    args = parser.parse_args()
    if args.check in ("flow", "time", "time2", "chat") and not args.app_url:
        raise SystemExit(
            f"{args.check} saves and runs: give --app-url of a copy (snapshot.py)"
        )

    suffix = int(
        json.loads((ROOT / ".claude/project.config.json").read_text())["portSuffix"]
    )
    named = f"{args.check}-{args.name}" if args.name else args.check
    request = (HERE / f"{args.check}.md").read_text().format(
        url=args.app_url or f"http://127.0.0.1:{3000 + suffix}",
        context=f"ui-audit-{named}",
        datasets=args.datasets,
        scenarios=scenarios(args.scenarios),
        root=ROOT,
        images=ROOT.parent / "annotation_images",
    ) + TYPING
    out = ROOT / "logs/ui-audit"
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"{datetime.now(UTC):%Y%m%dT%H%MZ}-{named}"
    result = Path(f"{stem}.result.md")
    empty = out / "empty"  # the model's working folder: nothing of the repository in it
    empty.mkdir(exist_ok=True)
    # The repository's .codex/config.toml names the same server "chrome-devtools" with a list
    # of approved tools; set that one, so there is a single server with every tool approved
    # (found 2026-10-06: under another name, the model used the repository's and could not
    # close its own tab).
    common = [
        "--skip-git-repo-check", "--json",
        "-c", 'mcp_servers.chrome-devtools.command="npx"',
        "-c", f'mcp_servers.chrome-devtools.args=["-y","chrome-devtools-mcp@latest","--browser-url=http://127.0.0.1:{9000 + suffix}"]',
        "-c", 'mcp_servers.chrome-devtools.default_tools_approval_mode="approve"',
        "-c", "mcp_servers.chrome-devtools.startup_timeout_sec=60",
        "-c", "mcp_servers.chrome-devtools.tool_timeout_sec=120",
        "-c", f'model_reasoning_effort="{args.effort}"',
        "-c", 'approval_policy="never"',
        "--output-last-message", str(result),
        *(["-c", f'service_tier="{args.tier}"'] if args.tier else []),
    ]  # fmt: skip
    thread = None
    for attempt in range(args.tries):
        log = Path(f"{stem}.{attempt}.jsonl")
        if thread is None:
            argv = ["codex", "exec", "--model", args.model, "--sandbox", "read-only",
                    "-C", str(empty), *common, "-"]  # fmt: skip
            stdin = request
        else:
            # "Selected model is at capacity" and the like: go on in the same session.
            argv = ["codex", "exec", "resume", thread, "--model", args.model,
                    "-c", 'sandbox_mode="read-only"', *common,
                    RESUME]  # fmt: skip
            stdin = None
        with log.open("w") as output:
            subprocess.run(
                argv,
                input=stdin,
                text=True,
                stdout=output,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        lines = log.read_text().splitlines()
        if thread is None and lines:
            try:
                thread = json.loads(lines[0]).get("thread_id")
            except ValueError:
                pass
        if result.exists() and result.read_text().strip():
            print(result)
            return
        print(
            f"try {attempt} ended without a report: {lines[-1][:160] if lines else '-'}"
        )
        time.sleep(300)
    raise SystemExit(f"No report after {args.tries} tries; see {stem}.*.jsonl")


def scenarios(ids):
    """The scenarios of these ids (\"C01,S03\"), each its section of the scenarios' document, in
    the order given."""
    if not ids:
        return ""
    text = (ROOT / "docs/2026-10-28-chat-test-scenarios.md").read_text()
    sections = {}
    for part in text.split("\n### ")[1:]:
        body = part.split("\n## ")[0].rstrip()
        sections[body.split(" ", 1)[0]] = "### " + body
    missing = [i for i in ids.split(",") if i not in sections]
    if missing:
        raise SystemExit(f"No such scenario: {', '.join(missing)}")
    return "\n\n".join(sections[i] for i in ids.split(","))


if __name__ == "__main__":
    main()
