"""Where the workers' answers spent their time (docs/2026-10-16-ontology-definition.md 47):
each answer of a dataset's steward and of the reception, with its wait in the line (asked to
begun), its whole time, the time its tool calls took (calls at once counted once) and the rest
(the model's own turn), and its tools by time; then every tool's count and time over the answers
shown. Reads the database read-only.
Answers written before the tool times were kept show no split.

uv run --project agent_app python agent_app/tools/answer_times.py [--db PATH] [--since YYYY-MM-DD]
    [--limit N]
"""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JST = timezone(timedelta(hours=9))


def _rows(db, since, until):
    """The answers that took time, every worker's (one table since definition 48; the library's
    have no dataset), oldest first."""
    found = db.execute(
        "SELECT e.created_at, e.agent, d.name AS place, e.model, e.elapsed_ms,"
        " e.tools_json, j.created_at AS asked_at, j.started_at FROM agent_events e"
        " LEFT JOIN datasets d ON d.id=e.dataset_id LEFT JOIN jobs j ON j.id=e.job_id"
        " WHERE e.elapsed_ms IS NOT NULL AND e.created_at >= ? AND e.created_at < ?"
        " ORDER BY 1",
        (since, until),
    ).fetchall()
    return [dict(r) for r in found]


def _tools_ms(tools):
    """The time the calls took, those at once counted once; None when a call has no times."""
    if any(t.get("ms") is None for t in tools):
        return None
    spans = sorted((t["at"], t["at"] + t["ms"]) for t in tools)
    total, end = 0, None
    for start, stop in spans:
        if end is None or start > end:
            total += stop - start
            end = stop
        elif stop > end:
            total += stop - end
            end = stop
    return total


def _by_tool(tools):
    """Per tool: how many calls and their time (ms; None when a call has no times)."""
    found = {}
    for t in tools:
        count, ms = found.get(t["tool"], (0, 0))
        found[t["tool"]] = (
            count + 1,
            None if ms is None or t.get("ms") is None else ms + t["ms"],
        )
    return found


def _s(ms):
    return "-" if ms is None else f"{ms / 1000:.1f}"


def when(text):
    """An ISO time as the server writes it (UTC, Z)."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def between(start, end):
    """Milliseconds from one ISO time to another; None when either is missing."""
    if not start or not end:
        return None
    return (when(end) - when(start)).total_seconds() * 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", default=str(REPO / "agent_app/agent.db"))
    parser.add_argument("--since", default="1970-01-01", help="YYYY-MM-DD or ISO (UTC)")
    parser.add_argument("--until", default="9999", help="YYYY-MM-DD or ISO (UTC)")
    parser.add_argument("--limit", type=int, default=30, help="the newest N answers")
    args = parser.parse_args()
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    rows = _rows(db, args.since, args.until)[-args.limit :]
    print(
        "時刻(JST)    係        場所                  モデル             待ちs  全体s  道具s  残りs  道具（回数 秒）"
    )
    totals = {}
    for r in rows:
        tools = json.loads(r["tools_json"] or "[]")
        # No list kept (the reception's answers before 47): not known, not none.
        tools_ms = None if r["tools_json"] is None else _tools_ms(tools) if tools else 0
        rest = None if tools_ms is None else r["elapsed_ms"] - tools_ms
        at = when(r["created_at"])
        named = ", ".join(
            f"{tool}×{count} {_s(ms)}"
            for tool, (count, ms) in sorted(
                _by_tool(tools).items(), key=lambda kv: -(kv[1][1] or 0)
            )
        )
        print(
            f"{at.astimezone(JST):%m-%d %H:%M}  {r['agent']:<9} {(r['place'] or 'ライブラリ')[:18]:<20}"
            f" {(r['model'] or '-')[:18]:<18} {_s(between(r['asked_at'], r['started_at'])):>5}"
            f" {_s(r['elapsed_ms']):>6} {_s(tools_ms):>6}"
            f" {_s(rest):>6}  {named}"
        )
        for tool, (count, ms) in _by_tool(tools).items():
            c, m = totals.get(tool, (0, 0))
            totals[tool] = (c + count, None if m is None or ms is None else m + ms)
    if totals:
        print("\n道具ごと（表の答えの合計）: 道具  回数  合計s  1回の平均s")
        for tool, (count, ms) in sorted(
            totals.items(), key=lambda kv: -(kv[1][1] or 0)
        ):
            mean = None if ms is None else ms / count
            print(f"  {tool:<20} {count:>4} {_s(ms):>7} {_s(mean):>7}")


if __name__ == "__main__":
    main()
