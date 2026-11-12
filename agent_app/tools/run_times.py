"""Where the annotation runs spent their time (the workers' answers are answer_times.py's,
docs/2026-10-16-ontology-definition.md 47): each run with its whole time, and each image's
start in it (a run waits for slots there) and time split into the start (the work AI's CLI up and its
first word), its tool calls by tool, and the rest (the model's own turns). Then every tool's
count and time over the images shown. Reads the database read-only.

uv run --project agent_app python agent_app/tools/run_times.py [--db PATH] [--since ISO]
"""

import argparse
import json
import sqlite3

from answer_times import JST, REPO, _s, between, when


def _runs(db, since, until):
    """The runs begun since then, oldest first, with their dataset, model and kind."""
    found = db.execute(
        "SELECT r.id, r.number, r.status, r.started_at, r.ended_at, r.elapsed_ms,"
        " d.name AS place, json_extract(r.settings_json, '$.model') AS model,"
        " json_extract(r.settings_json, '$.effort') AS effort,"
        " json_extract(r.settings_json, '$.trial_instruction') IS NOT NULL AS trial"
        " FROM runs r JOIN datasets d ON d.id=r.dataset_id"
        " WHERE r.started_at >= ? AND r.started_at < ? ORDER BY r.started_at",
        (since, until),
    ).fetchall()
    return [dict(r) for r in found]


def _image(db, result):
    """One image's time: the start, its tool calls by tool, and the rest."""
    logs = db.execute(
        "SELECT at, kind, payload_json FROM run_logs WHERE result_id=? ORDER BY seq",
        (result["id"],),
    ).fetchall()
    first = next((r["at"] for r in logs if r["kind"] == "agent"), None)
    tools = {}
    for r in logs:
        if r["kind"] != "tool":
            continue
        payload = json.loads(r["payload_json"])
        count, ms = tools.get(payload.get("tool"), (0, 0))
        tools[payload.get("tool")] = (count + 1, ms + (payload.get("duration_ms") or 0))
    used = sum(ms for _, ms in tools.values())
    start = between(result["started_at"], first)
    rest = (
        None
        if result["elapsed_ms"] is None
        else result["elapsed_ms"] - used - (start or 0)
    )
    return start, tools, used, rest


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", default=str(REPO / "agent_app/agent.db"))
    parser.add_argument("--since", default="1970-01-01", help="ISO time (UTC)")
    parser.add_argument("--until", default="9999", help="ISO time (UTC)")
    args = parser.parse_args()
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    totals = {}
    for run in _runs(db, args.since, args.until):
        kind = "見本" if run["trial"] else "依頼"
        print(
            f"\n記録{run['number']} {kind} {run['place']}  {run['model']} {run['effort']}"
            f"  {when(run['started_at']).astimezone(JST):%m-%d %H:%M:%S}"
            f"  全体 {_s(run['elapsed_ms'])}s  {run['status']}"
        )
        print(
            "    画像              始まりs  全体s  起動s  道具s  残りs  道具（回数 秒）"
        )
        for result in db.execute(
            "SELECT x.id, x.started_at, x.elapsed_ms, x.status, i.name FROM results x"
            " JOIN images i ON i.id=x.image_id WHERE x.run_id=? ORDER BY x.position",
            (run["id"],),
        ):
            start, tools, used, rest = _image(db, result)
            began = between(run["started_at"], result["started_at"])
            named = ", ".join(
                f"{tool}×{count} {_s(ms)}"
                for tool, (count, ms) in sorted(tools.items(), key=lambda kv: -kv[1][1])
            )
            print(
                f"    {result['name'][:16]:<16} {_s(began):>7} {_s(result['elapsed_ms']):>6}"
                f" {_s(start):>6} {_s(used):>6} {_s(rest):>6}  {result['status']}  {named}"
            )
            for tool, (count, ms) in tools.items():
                c, m = totals.get(tool, (0, 0))
                totals[tool] = (c + count, m + ms)
    if totals:
        print("\n作業 AI の道具ごと（表の画像の合計）: 道具  回数  合計s  1回の平均s")
        for tool, (count, ms) in sorted(totals.items(), key=lambda kv: -kv[1][1]):
            print(f"  {tool:<20} {count:>4} {_s(ms):>7} {_s(ms / count):>7}")


if __name__ == "__main__":
    main()
