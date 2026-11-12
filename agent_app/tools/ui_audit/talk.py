"""Talk with the app's workers as a person does on the screen, through the same API (definition
74: the tests of the workers send the person's lines, press options and decisions, and read
what reached the screen). For the copy (snapshot.py, 4110) unless --url says otherwise.

    talk.py new PLACE AGENT                     a new chat; prints its number
    talk.py say PLACE AGENT CHAT TEXT           the person's line; waits; the new lines
    talk.py choose PLACE AGENT CHAT LINE OPTION a question's option (1, 2, ...); waits
    talk.py decide BOX [--decline] [--args J]   a decision pressed (or not); waits for the work
                                                it starts unless --nowait
    talk.py lines PLACE AGENT CHAT              the chat's lines
    talk.py state PLACE                         what waits, the plan's state, the jobs
    talk.py check DB [--since ISO]              invariants.py on the copy's database

PLACE: library, or a dataset's number (#34 or 34) or id. AGENT: reception or steward.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

HEADERS = {"X-Actor": "ui", "Accept-Language": "ja"}


def client(url):
    return httpx.Client(base_url=url + "/v1", headers=HEADERS, timeout=60)


def place_path(api, place):
    if place == "library":
        return "/library"
    number = place.lstrip("#")
    if number.isdigit():
        found = next(
            d
            for d in api.get("/datasets").json()["datasets"]
            if d["number"] == int(number)
        )
        return f"/datasets/{found['id']}"
    return f"/datasets/{place}"


def settle(api, limit=900):
    """Waits until nothing goes or waits in the line of work (answers and runs)."""
    for _ in range(limit):
        jobs = api.get("/jobs").json()
        if not jobs["running"] and not jobs["queued"]:
            return
        time.sleep(2)
    print("(still going after the wait)")


def answered(api, job_id, limit=600):
    """Waits for one answer (its job), not for the runs going: a person writes again while a
    run goes ("stop it")."""
    for _ in range(limit):
        found = api.get("/jobs").json()["jobs"]
        job = next((j for j in found if j["id"] == job_id), None)
        if job is None or job["state"] not in ("queued", "running"):
            return
        time.sleep(2)
    print("(the answer still going after the wait)")


def show(api, base, agent, chat, after=0):
    events = api.get(f"{base}/agents/{agent}/events", params={"chat": chat}).json()
    for e in events["events"]:
        if e["id"] <= after:
            continue
        data = e.get("data") or {}
        head = f"#{e['id']} {e['kind']} ({e['by']})"
        print(f"{head}: {e['text']}")
        for i, option in enumerate(data.get("options") or [], 1):
            print(
                f"    {i}. {option.get('label')}{' (recommended)' if option.get('recommend') else ''}"
            )
        for box in data.get("proposal_ids") or []:
            found = api.get(f"/proposals/{box}").json()
            print(f"    decision {box}: {found['title']} [{found['state']}]")
        if data.get("show"):
            print(f"    shows: {json.dumps(data['show'], ensure_ascii=False)}")
        if data.get("parts"):
            print(f"    parts: {json.dumps(data['parts'], ensure_ascii=False)}")
        if data.get("code"):
            print(f"    code: {data['code']}")
        if e["closed_at"] and e["kind"] == "question":
            print("    (closed)")
    return events["events"][-1]["id"] if events["events"] else after


# The screen's dictionary: the server's own options are worded by the screen (lib/talk.ts
# optionWords), and the person's line says them so.
JA = json.loads(
    (Path(__file__).resolve().parents[2] / "ui/src/i18n/ja.json").read_text(
        encoding="utf-8"
    )
)


def screen_words(option):
    """An option's words as the screen shows them (a worker's as it wrote them)."""
    say, values = option.get("say"), option.get("values") or {}
    if not say:
        return option["label"]
    if say == "plan":
        what = "・".join(label["name"] for label in values.get("labels") or [])
        key = "entry.o.plan" if values.get("done") else "entry.o.plan.none"
        return JA[key].format(
            what=what, done=values.get("done"), total=values.get("total")
        )
    return JA[f"entry.o.{say}"].format(
        n=values.get("n", 0), count=values.get("count", 0)
    )


def last_id(api, base, agent, chat):
    events = api.get(f"{base}/agents/{agent}/events", params={"chat": chat}).json()
    return events["events"][-1]["id"] if events["events"] else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", default="http://127.0.0.1:4110")
    sub = parser.add_subparsers(dest="do", required=True)
    for name, args in (
        ("new", ["place", "agent"]),
        ("say", ["place", "agent", "chat", "text"]),
        ("choose", ["place", "agent", "chat", "line", "option"]),
        ("lines", ["place", "agent", "chat"]),
        ("state", ["place"]),
    ):
        command = sub.add_parser(name)
        for arg in args:
            command.add_argument(arg)
    decide = sub.add_parser("decide")
    decide.add_argument("box")
    decide.add_argument("--decline", action="store_true")
    decide.add_argument("--args", help="Values changed before deciding, as JSON.")
    decide.add_argument(
        "--nowait", action="store_true", help="Not wait for what it starts."
    )
    check = sub.add_parser("check")
    check.add_argument("db")
    check.add_argument("--since", default="")
    a = parser.parse_args()
    if a.do == "check":
        import subprocess

        here = Path(__file__).resolve().parent
        argv = [sys.executable, str(here / "invariants.py"), a.db, "--since", a.since]
        sys.exit(subprocess.run(argv, check=False).returncode)
    with client(a.url) as api:
        if a.do == "decide":
            if a.decline:
                answer = api.post(f"/proposals/{a.box}/decline", json={})
            else:
                body = {"args": json.loads(a.args)} if a.args else {}
                answer = api.post(f"/proposals/{a.box}/apply", json=body)
            found = answer.json()
            print(found.get("state") or json.dumps(found, ensure_ascii=False)[:400])
            if not a.nowait:
                time.sleep(3)
                settle(api)
            return
        base = place_path(api, a.place)
        if a.do == "new":
            print(api.post(f"{base}/agents/{a.agent}/chats", json={}).json()["id"])
        elif a.do == "lines":
            show(api, base, a.agent, int(a.chat))
        elif a.do == "say":
            after = last_id(api, base, a.agent, int(a.chat))
            sent = api.post(
                f"{base}/agents/{a.agent}/messages",
                json={"text": a.text, "chat_id": int(a.chat)},
            )
            if sent.status_code >= 400:
                print(sent.text)
                return
            answered(api, sent.json()["job_id"])
            show(api, base, a.agent, int(a.chat), after)
        elif a.do == "choose":
            chat = int(a.chat)
            lines = api.get(
                f"{base}/agents/{a.agent}/events", params={"chat": chat}
            ).json()
            question = next(
                (e for e in lines["events"] if e["id"] == int(a.line)), None
            )
            after = last_id(api, base, a.agent, chat)
            options = (question or {}).get("data", {}).get("options") or []
            index = int(a.option) - 1
            words = screen_words(options[index]) if 0 <= index < len(options) else None
            answer = api.post(
                f"{base}/agents/{a.agent}/events/{a.line}/answer",
                json={"option": index, **({"words": words} if words else {})},
            )
            if answer.status_code >= 400:
                print(answer.text)
                return
            job = answer.json().get("job_id")
            if job:
                answered(api, job)
            show(api, base, a.agent, chat, after)
        elif a.do == "state":
            if base != "/library":
                plan = api.get(f"{base}/plan/state").json()
                print("plan: next", plan.get("next"), "version", plan.get("revision"))
            for box in api.get(f"{base}/proposals").json()["proposals"]:
                if box["state"] == "open":
                    print(f"waiting decision {box['id']}: {box['title']}")
            jobs = api.get("/jobs").json()
            print(f"jobs running {jobs['running']} queued {jobs['queued']}")


if __name__ == "__main__":
    main()
