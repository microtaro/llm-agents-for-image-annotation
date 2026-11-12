"""The agent app's first step (docs/2026-10-09-agent-app-design.md 3): firm boxes (their stage
and step from what they change, their author kept, a run of a box told to its author), the runs'
default model and Haiku's warning, and the dataset's notes."""

import asyncio

from test_agents import _agent_headers, fake_turns
from test_drafts_and_ai import mcp
from test_runs import finished, scenario

from agent_app import agent_answer
from agent_app import runs as runs_module


def test_a_box_is_of_the_step_it_changes_and_its_run_tells_its_author(
    tmp_path, monkeypatch
):
    # User 2026-10-09: any worker may make any box; the box is of the map's place by what it
    # changes, its maker is its author, and the run it starts ends in the author's talk.
    async def body(app, client, dataset, ids):
        release = asyncio.Event()
        real = runs_module.infer

        async def held(*args):
            await release.wait()
            return await real(*args)

        monkeypatch.setattr(runs_module, "infer", held)
        base = f"/v1/datasets/{dataset}/proposals"
        run = {
            "agent": "steward",
            "tool": "run_start",
            "args": {"image_ids": [ids["a.png"]], "budget_per_image_usd": "1"},
            "title": "a を流す",
            "reason": "r",
        }
        box = (await client.post(base, json=run)).json()
        assert (box["agent"], box["stage"], box["step"]) == (
            "steward",
            "production",
            "run",
        )
        # Opus 5.5 unless asked; Haiku 5.5 when asked, with its warning.
        assert box["args"]["model"] == "claude-opus-5-5"
        assert box["preview"]["warning"] is None
        cheap = {**run, "args": {**run["args"], "model": "claude-haiku-5-5"}}
        newer = (await client.post(base, json=cheap)).json()
        assert newer["preview"]["warning"] == "haiku_accuracy"
        # The newer run replaced the first (definition 40.1): it is the one decided, and it
        # says so to its maker (2026-10-29: the worker said the one replaced still waited).
        assert newer["replaced"] == [{"id": box["id"], "title": "a を流す"}]
        applied = (await client.post(f"/v1/proposals/{newer['id']}/apply")).json()
        run_id = applied["outcome"]["id"]
        job = app.state.db.one("SELECT agent FROM jobs WHERE run_id=?", (run_id,))
        assert job["agent"] == "steward"
        stop = {
            **run,
            "tool": "run_stop",
            "args": {"run_id": run_id},
            "title": "止める",
        }
        stop = (await client.post(base, json=stop)).json()
        release.set()
        await finished(client, run_id)
        # The run ended by itself: its stop is withdrawn then, not at the next write (2026-10-29:
        # "stop record 3" waited 40 s after record 3 had ended).
        assert (await client.get(f"/v1/proposals/{stop['id']}")).json()[
            "state"
        ] == "withdrawn"
        events = (
            await client.get(f"/v1/datasets/{dataset}/agents/steward/events")
        ).json()["events"]
        assert any(e["text"] == "run_ended" for e in events)

    scenario(tmp_path, monkeypatch, body)


def test_a_run_that_ended_with_failures_names_the_images_not_done(
    tmp_path, monkeypatch
):
    # The 50 images' test 2026-10-29: "ended with failures (38/47)" was followed by the first
    # ten images of the record, read as the failed ones.
    async def body(app, client, dataset, ids):
        run = {
            "agent": "steward",
            "tool": "run_start",
            "args": {"image_ids": [ids["a.png"], ids["fail.png"]]},
            "title": "流す",
            "reason": "r",
        }
        box = (await client.post(f"/v1/datasets/{dataset}/proposals", json=run)).json()
        applied = (await client.post(f"/v1/proposals/{box['id']}/apply")).json()
        await finished(client, applied["outcome"]["id"])
        events = (
            await client.get(f"/v1/datasets/{dataset}/agents/steward/events")
        ).json()["events"]
        ended = next(e for e in events if e["text"] == "run_ended")["data"]
        assert (ended["images"], ended["not_done"]) == (["fail.png"], True)

    scenario(tmp_path, monkeypatch, body)


def test_a_note_keeps_its_worker_and_every_worker_reads_it(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        async with mcp(app, _agent_headers(dataset, "steward")) as worker:
            out = await worker.call_tool(
                "note_write",
                {"dataset_id": dataset, "text": "E004 は Haiku で読めない"},
            )
            assert not out.is_error, out.structured_content
        notes = (await client.get(f"/v1/datasets/{dataset}/notes")).json()["notes"]
        assert [(n["agent"], n["text"]) for n in notes] == [
            ("steward", "E004 は Haiku で読めない")
        ]
        told = agent_answer.dataset_context(app.state.db, dataset, "steward")["notes"]
        assert told == [{"by": "steward", "text": "E004 は Haiku で読めない"}]

    scenario(tmp_path, monkeypatch, body)


def test_what_the_person_looked_at_goes_with_the_words(tmp_path, monkeypatch):
    # Prototype 2 (Sol 2026-10-08, round 5): "this box" is understood only with the image the
    # person was looking at; it is kept on the line and given to the worker.
    async def body(app, client, dataset, ids):
        calls = fake_turns(
            app, monkeypatch, lambda call: {"kind": "answer", "message": "ok"}
        )
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        # The record chosen and the plan seen go too (definition 36.6: they did not).
        looking = {
            "stage": "production",
            "image_id": ids["a.png"],
            "image_name": "a.png",
            "record_id": "r1",
            "record_number": 7,
            "revision": 4,
        }
        path = f"/v1/datasets/{dataset}/agents/steward"
        asked = await client.post(
            f"{path}/messages",
            json={"text": "この枠ずれてない？", "looking_at": looking},
        )
        assert asked.status_code == 202, asked.text
        for _ in range(500):
            if calls:
                break
            await asyncio.sleep(0.01)
        assert calls[0]["context"]["looking_at"]["image_name"] == "a.png"
        assert calls[0]["context"]["looking_at"]["record_number"] == 7
        assert calls[0]["context"]["looking_at"]["revision"] == 4
        events = (await client.get(f"{path}/events")).json()["events"]
        assert events[0]["data"]["looking_at"]["image_name"] == "a.png"

    scenario(tmp_path, monkeypatch, body)


def test_a_chat_is_answered_in_the_language_of_the_persons_screen(
    tmp_path, monkeypatch
):
    # Found 2026-10-26 (definition 53): asked in English on the English screen, the reception
    # answered in Japanese; the worker was not told the screen's language. A turn the server
    # starts in the chat (after a run) goes on in it.
    async def body(app, client, dataset, ids):
        calls = fake_turns(
            app, monkeypatch, lambda call: {"kind": "answer", "message": "ok"}
        )
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        path = f"/v1/datasets/{dataset}/agents/steward"
        chat = (await client.post(f"{path}/chats", json={})).json()["id"]
        for turn, headers in enumerate(({"Accept-Language": "en"}, {})):
            asked = await client.post(
                f"{path}/messages",
                json={"text": "How many images?", "chat_id": chat},
                headers=headers,
            )
            assert asked.status_code == 202, asked.text
            for _ in range(500):
                if len(calls) > turn:
                    break
                await asyncio.sleep(0.01)
        assert [c["context"].get("language") for c in calls] == ["English", "English"]

    scenario(tmp_path, monkeypatch, body)


def test_the_workers_are_sent_to_the_server_they_started_on(tmp_path, monkeypatch):
    # 2026-10-09: the copy's port file was put back to the main one while the copy ran, and
    # its workers' tools went to the old app's server. The port is read once.
    from agent_app import config

    (tmp_path / ".claude").mkdir()
    port_file = tmp_path / ".claude/project.config.json"
    port_file.write_text('{"portSuffix": "1110"}')
    monkeypatch.setattr(config, "REPO", tmp_path)
    # Not the port file a run of the app left here (2026-11-11: 3901 in a clone, after 3900 was
    # taken).
    monkeypatch.setattr(config, "PORT_FILE", tmp_path / "server.port")
    config._project_port.cache_clear()
    try:
        assert config.base_url() == "http://127.0.0.1:4110"
        port_file.write_text('{"portSuffix": "110"}')
        assert config.base_url() == "http://127.0.0.1:4110"
        # A folder given to someone has no project file (user 2026-10-28: the zip).
        port_file.unlink()
        assert config.base_url() == f"http://127.0.0.1:{config.PORT_GIVEN}"
    finally:
        config._project_port.cache_clear()


def test_a_worker_has_chats_and_each_goes_on_by_itself(tmp_path, monkeypatch):
    # User 2026-10-09: chats as in any chat app. A new chat carries on neither the old CLI
    # session nor the old lines; a box's lines go to the chat it was asked in; deleting a
    # chat leaves its boxes.
    async def body(app, client, dataset, ids):
        from agent_app.agent_chat import add, current_chat

        db = app.state.db
        path = f"/v1/datasets/{dataset}/agents/steward"
        first = current_chat(db, dataset, "steward")
        asked = add(db, dataset, "steward", "human", "前の頼み", by_actor="person")
        add(
            db,
            dataset,
            "steward",
            "ai",
            "前の答え",
            session_id="s-old",
            model="claude-sonnet-5-5",
            prompt_sha=agent_answer.ROLES["steward"].sha,
        )
        answers = agent_answer.Answers(db, None)
        model = "claude-sonnet-5-5"
        assert answers._session(dataset, "steward", model, first) == "s-old"
        second = (await client.post(f"{path}/chats")).json()["id"]
        assert answers._session(dataset, "steward", model, second) is None
        # A box asked in the first chat and decided there: its decision is told there, not in
        # the second (definition 81: told in the chat it was decided in).
        box = (
            await client.post(
                f"/v1/datasets/{dataset}/proposals",
                json={
                    "agent": "steward",
                    "tool": "mark",
                    "args": {
                        "target": "image",
                        "image_id": ids["a.png"],
                        "excluded": True,
                    },
                    "title": "a を外す",
                    "reason": "r",
                },
            )
        ).json()
        db.execute("UPDATE proposals SET chat_id=? WHERE id=?", (first, box["id"]))
        await client.post(
            f"/v1/proposals/{box['id']}/decline", json={}, params={"chat": first}
        )
        listed = (await client.get(f"{path}/chats")).json()["chats"]
        assert {c["id"] for c in listed} == {first, second}
        lines = (await client.get(f"{path}/events?chat={first}")).json()["events"]
        assert [e["text"] for e in lines][-1] == "box_declined"
        assert (await client.get(f"{path}/events?chat={second}")).json()["events"] == []
        from agent_app.agent_chat import worker_lines

        there = add(
            db,
            dataset,
            "steward",
            "human",
            "新しい頼み",
            by_actor="person",
            chat_id=second,
        )
        assert worker_lines(db, there, "steward")["earlier"] == []
        deleted = await client.delete(f"{path}/chats/{first}")
        assert deleted.status_code == 200, deleted.text
        # Hidden, its lines kept: what was made from them still says which (issue #4 F-09).
        listed = (await client.get(f"{path}/chats")).json()["chats"]
        assert {c["id"] for c in listed} == {second}
        assert db.one("SELECT 1 FROM agent_events WHERE id=?", (asked,)) is not None
        assert (await client.get(f"/v1/proposals/{box['id']}")).json()[
            "state"
        ] == "declined"

    scenario(tmp_path, monkeypatch, body)


def test_a_box_made_again_waits_alone(tmp_path, monkeypatch):
    # User 2026-10-09: after "ask to remake", the old line still opened the old red box and
    # both stood in the band. Since 2026-10-17 the old one is withdrawn when what it stood on
    # changed (definition 18.13), so the one made again is the only one waiting.
    async def body(app, client, dataset, ids):
        base = f"/v1/datasets/{dataset}/proposals"
        mark = {
            "agent": "steward",
            "tool": "mark",
            "args": {"target": "image", "image_id": ids["a.png"], "excluded": True},
            "title": "a を外す",
            "reason": "r",
        }
        old = (await client.post(base, json=mark)).json()
        image = f"/v1/datasets/{dataset}/images/{ids['a.png']}"
        await client.post(f"{image}/exclude", json={})
        listed = (await client.get(base)).json()["proposals"]
        assert next(p for p in listed if p["id"] == old["id"])["state"] == "withdrawn"
        new = (await client.post(base, json=mark)).json()
        listed = (await client.get(base)).json()["proposals"]
        assert [p["id"] for p in listed if p["state"] == "open"] == [new["id"]]

    scenario(tmp_path, monkeypatch, body)


def test_an_answer_about_a_waiting_box_links_it(tmp_path, monkeypatch):
    # User 2026-10-09: "the save proposal waits" (made in an earlier answer) had no link on
    # the line. The heavy answer names the waiting boxes it is about; they are linked.
    async def body(app, client, dataset, ids):

        base = f"/v1/datasets/{dataset}"
        waiting = (
            await client.post(
                f"{base}/proposals",
                json={
                    "agent": "steward",
                    "tool": "mark",
                    "args": {
                        "target": "image",
                        "image_id": ids["a.png"],
                        "excluded": True,
                    },
                    "title": "a を外す",
                    "reason": "r",
                },
            )
        ).json()

        async def turn(self, job, text, looking, settings, session, record):
            answer = {
                "kind": "answer",
                "message": "外す提案が待っています",
                "question": None,
            }
            said = {**answer, "handoff": None}
            return {**said, "boxes": [waiting["id"], "prp-unknown"]}, None, None

        monkeypatch.setattr(agent_answer.Answers, "_turn", turn)
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "gpt-6.1-sol", "effort": "medium"},
        )
        await client.post(
            f"{base}/agents/steward/messages", json={"text": "どうなってる？"}
        )
        for _ in range(500):
            events = (await client.get(f"{base}/agents/steward/events")).json()[
                "events"
            ]
            if events[-1]["kind"] == "ai":
                break
            await asyncio.sleep(0.01)
        assert events[-1]["data"]["proposal_ids"] == [waiting["id"]]

    scenario(tmp_path, monkeypatch, body)


def test_a_worker_reads_its_chat_as_the_person_sees_it(tmp_path, monkeypatch):
    # User 2026-10-29: the steward named the eight values before its question and only the
    # question was shown; swept, a server's question and the person's choice of it never
    # reached a worker going on, and a request the reception handed over came as the person's
    # own words (definition 68.1).
    async def body(app, client, dataset, ids):
        from agent_app.agent_chat import add, new_chat, worker_lines

        db = app.state.db
        chat = new_chat(db, dataset, "steward")

        def line(kind, text, by, data=None):
            return add(
                db, dataset, "steward", kind, text, by_actor=by, chat_id=chat, data=data
            )

        line("human", "始めて", "person")
        line("ai", "見ました", "agent:steward")
        options = [{"label": "Make a new plan"}, {"label": "Use an existing plan"}]
        line(
            "question",
            "How is this plan made?",
            "server",
            {"options": options, "answered": {"option": 0}},
        )
        line("human", "白紙から新しく作る", "person", {"answer_to": 3})
        line("note", "run_ended", "server", {"note": "run_ended"})
        asked = line("human", "続けて", "person")
        read = worker_lines(db, asked, "steward")
        assert [(r["by"], r["kind"]) for r in read["earlier"]][:2] == [
            ("person", "human"),
            ("you", "ai"),
        ]
        assert read["since"] == [
            {
                "by": "server",
                "kind": "question",
                "text": "How is this plan made?",
                "options": ["Make a new plan", "Use an existing plan"],
                "chosen": "Make a new plan",
            },
            {"by": "person", "kind": "human", "text": "白紙から新しく作る"},
            {"by": "server", "kind": "note", "text": "run_ended"},
        ]
        assert read["request"] == {"by": "person"}
        # Handed by the reception: its summary is its own, the person's words come with it.
        library = new_chat(db, None, "reception")
        add(
            db,
            None,
            "reception",
            "human",
            "#8 の箱の値を読みたい",
            by_actor="person",
            chat_id=library,
        )
        offer = add(
            db,
            None,
            "reception",
            "handoff_offer",
            "伝えます",
            chat_id=library,
            data={
                "agent": "steward",
                "summary": "箱の値を読む（試験D がもとにできる）",
            },
        )
        handed = add(
            db,
            dataset,
            "steward",
            "human",
            "箱の値を読む（試験D がもとにできる）",
            by_actor="agent:reception",
            chat_id=new_chat(db, dataset, "steward"),
            data={"from_agent": "reception", "from_event_id": offer},
        )
        request = worker_lines(db, handed, "steward")["request"]
        assert request["by"] == "reception"
        assert [(r["by"], r["text"]) for r in request["handed_from"]] == [
            ("person", "#8 の箱の値を読みたい"),
            ("reception", "伝えます"),
        ]

    scenario(tmp_path, monkeypatch, body)


def test_what_a_restart_stopped_is_said_where_it_was_asked(tmp_path, monkeypatch):
    # 2026-10-29, swept after the fixes of the day: a restart failed an answer going and
    # interrupted a run going without a word in the talk (the answer's question stayed closed,
    # and a waiting stop of the run waited on). Said as when they end (definition 72).
    async def body(app, client, dataset, ids):
        from agent_app.agent_chat import add, new_chat
        from agent_app.app import create_app

        db = app.state.db
        release = asyncio.Event()
        real = runs_module.infer

        async def held(*args):
            await release.wait()
            return await real(*args)

        monkeypatch.setattr(runs_module, "infer", held)
        base = f"/v1/datasets/{dataset}/proposals"
        run = {
            "agent": "steward",
            "tool": "run_start",
            "args": {"image_ids": [ids["a.png"]], "budget_per_image_usd": "1"},
            "title": "a を流す",
            "reason": "r",
        }
        box = (await client.post(base, json=run)).json()
        run_id = (await client.post(f"/v1/proposals/{box['id']}/apply")).json()[
            "outcome"
        ]["id"]
        stop = {
            **run,
            "tool": "run_stop",
            "args": {"run_id": run_id},
            "title": "止める",
        }
        stop = (await client.post(base, json=stop)).json()
        # An answer going: the person answered a question, and the worker was answering.
        chat = new_chat(db, dataset, "steward")
        asked = add(
            db,
            dataset,
            "steward",
            "question",
            "どれ？",
            chat_id=chat,
            data={"options": [{"label": "円"}], "answered": {"option": 0}},
        )
        db.execute("UPDATE agent_events SET closed_at='x' WHERE id=?", (asked,))
        line = add(
            db,
            dataset,
            "steward",
            "human",
            "円",
            by_actor="person",
            chat_id=chat,
            data={"answer_to": asked},
        )
        db.execute(
            "INSERT INTO jobs(id, dataset_id, agent, kind, title, state, request_event_id,"
            " created_at, chat_id) VALUES('job-going', ?, 'steward', 'answer_heavy',"
            " 'answer', 'running', ?, 'x', ?)",
            (dataset, line, chat),
        )
        while (
            db.one("SELECT status FROM runs WHERE id=?", (run_id,))["status"]
            != "running"
        ):
            await asyncio.sleep(0.01)
        # The server starts again on the same database (the first one still holding the run).
        again = create_app(db.path)
        async with again.router.lifespan_context(again):
            pass
        release.set()
        lines = db.execute(
            "SELECT kind, json_extract(data_json,'$.code') AS code,"
            " json_extract(data_json,'$.status') AS status FROM agent_events WHERE id>?",
            (line,),
        )
        assert ("failed", "app_stopped", None) in [tuple(r) for r in lines]
        assert ("note", None, "interrupted") in [tuple(r) for r in lines]
        assert (
            db.one("SELECT closed_at FROM agent_events WHERE id=?", (asked,))[0] is None
        )
        assert db.one("SELECT state FROM proposals WHERE id=?", (stop["id"],))[0] == (
            "withdrawn"
        )

    scenario(tmp_path, monkeypatch, body)


def test_a_run_the_app_closes_on_is_interrupted_not_failed(tmp_path, monkeypatch):
    # 2026-10-29: closing the app with a run going ended it as failed ("ended with failures"
    # in the talk); it is interrupted because the app stopped, as when the app ended without
    # closing (definition 72).
    async def body(app, client, dataset, ids):
        release = asyncio.Event()
        real = runs_module.infer

        async def held(*args):
            await release.wait()
            return await real(*args)

        monkeypatch.setattr(runs_module, "infer", held)
        box = (
            await client.post(
                f"/v1/datasets/{dataset}/proposals",
                json={
                    "agent": "steward",
                    "tool": "run_start",
                    "args": {"image_ids": [ids["a.png"]], "budget_per_image_usd": "1"},
                    "title": "a を流す",
                    "reason": "r",
                },
            )
        ).json()
        run_id = (await client.post(f"/v1/proposals/{box['id']}/apply")).json()[
            "outcome"
        ]["id"]
        db = app.state.db
        while (
            db.one("SELECT status FROM runs WHERE id=?", (run_id,))["status"]
            != "running"
        ):
            await asyncio.sleep(0.01)
        await app.state.runs.close()
        await app.state.jobs.close()
        ended = db.one("SELECT status, error_code FROM runs WHERE id=?", (run_id,))
        assert tuple(ended) == ("interrupted", "app_stopped")
        told = db.one(
            "SELECT json_extract(data_json,'$.status') FROM agent_events"
            " WHERE text='run_ended'"
        )
        assert told[0] == "interrupted"

    scenario(tmp_path, monkeypatch, body)


def test_a_box_an_answer_made_again_is_not_on_its_line(tmp_path, monkeypatch):
    # 2026-10-29 (the workers' tests S04, S08): in one answer the steward made a run's box and
    # made it again with another cost limit at once; the line showed both under one title, the
    # first withdrawn (definition 74).
    async def body(app, client, dataset, ids):
        db = app.state.db
        run = {
            "agent": "steward",
            "tool": "run_start",
            "args": {"image_ids": [ids["a.png"]], "budget_per_image_usd": "0.5"},
            "title": "a を流す",
            "reason": "r",
        }
        made = []

        async def turn(key, **given):
            job = db.one(
                "SELECT id FROM jobs WHERE kind='answer_heavy' AND state='running'"
            )
            headers = {"X-Annotation-Agent": "steward", "X-Annotation-Job": job["id"]}
            for budget in ("0.5", "1"):
                body = {**run, "args": {**run["args"], "budget_per_image_usd": budget}}
                made.append(
                    (
                        await client.post(
                            f"/v1/datasets/{dataset}/proposals",
                            json=body,
                            headers=headers,
                        )
                    ).json()["id"]
                )
            said = {"question": None, "handoff": None, "boxes": [], "show": None}
            return (
                {**said, "kind": "answer", "message": "用意しました"},
                None,
                {"session_id": "s"},
            )

        monkeypatch.setattr(app.state.jobs.residents, "turn", turn)
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        path = f"/v1/datasets/{dataset}/agents/steward"
        await client.post(f"{path}/messages", json={"text": "a を流して"})
        for _ in range(500):
            jobs = (await client.get("/v1/jobs")).json()
            if not jobs["running"] and not jobs["queued"]:
                break
            await asyncio.sleep(0.01)
        line = (await client.get(f"{path}/events")).json()["events"][-1]
        assert line["data"]["proposal_ids"] == [made[1]]

    scenario(tmp_path, monkeypatch, body)


def test_a_box_its_own_answer_withdrew_is_made_again(tmp_path, monkeypatch):
    # 2026-10-29 (10 images to the end): the steward made the samples' box, then wrote the
    # plan, which withdrew it; it said the box was ready, and none waited (definition 76).
    from test_runs import DEFINITIONS

    async def body(app, client, dataset, ids):
        db = app.state.db
        base = f"/v1/datasets/{dataset}"
        made, turns = [], []

        async def turn(key, **given):
            turns.append(given["message"])
            job = db.one(
                "SELECT id FROM jobs WHERE kind='answer_heavy' AND state='running'"
            )
            headers = {"X-Annotation-Agent": "steward", "X-Annotation-Job": job["id"]}
            draft = {"text": "円を囲む", "label_definitions": DEFINITIONS}
            if len(turns) == 1:
                await client.put(
                    f"{base}/drafts/instruction", json=draft, headers=headers
                )
            box = {
                "agent": "steward",
                "tool": "run_start",
                "args": {"image_ids": [ids["a.png"]], "trial": True},
                "title": "見本",
                "reason": "r",
            }
            made.append(
                (
                    await client.post(f"{base}/proposals", json=box, headers=headers)
                ).json()
            )
            if len(turns) == 1:
                # Its own later write moves the plan the box holds.
                await client.put(
                    f"{base}/drafts/instruction",
                    json={**draft, "text": "円を1つずつ囲む"},
                    headers=headers,
                )
            said = {"question": None, "handoff": None, "boxes": [], "show": None}
            return (
                {**said, "kind": "answer", "message": "見本の決定を用意しました"},
                None,
                {"session_id": "s"},
            )

        monkeypatch.setattr(app.state.jobs.residents, "turn", turn)
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        await client.post(
            f"{base}/agents/steward/messages", json={"text": "見本を作って"}
        )
        for _ in range(500):
            jobs = (await client.get("/v1/jobs")).json()
            if not jobs["running"] and not jobs["queued"]:
                break
            await asyncio.sleep(0.01)
        assert len(turns) == 2 and '"part": "box"' in turns[1]
        line = (await client.get(f"{base}/agents/steward/events")).json()["events"][-1]
        assert line["data"]["proposal_ids"] == [made[1]["id"]]
        assert db.one("SELECT state FROM proposals WHERE id=?", (made[1]["id"],))[
            0
        ] == ("open")

    scenario(tmp_path, monkeypatch, body)


def test_a_dataset_made_says_the_files_it_was_made_without(tmp_path, monkeypatch):
    # 2026-10-29 (10 images to the end): 11 files made 9 images, one of the same content as
    # another and one broken, and nothing said which or why (definition 76).
    from PIL import Image

    async def body(app, client, dataset, ids):
        folder = tmp_path / "made"
        folder.mkdir()
        Image.new("RGB", (40, 30), (200, 10, 10)).save(folder / "a.png")
        (folder / "b_same.png").write_bytes((folder / "a.png").read_bytes())
        (folder / "c_broken.png").write_bytes(b"\x89PNG\r\n\x1a\nbroken")
        box = (
            await client.post(
                "/v1/library/proposals",
                json={
                    "agent": "reception",
                    "tool": "dataset_create",
                    "args": {
                        "name": "外れ値",
                        "purpose": "試す",
                        "paths": [str(folder)],
                    },
                    "title": "作る",
                    "reason": "r",
                },
            )
        ).json()
        applied = (await client.post(f"/v1/proposals/{box['id']}/apply")).json()
        skipped = {s["name"]: s for s in applied["outcome"]["skipped"]}
        assert skipped["b_same.png"] == {
            "name": "b_same.png",
            "reason": "same_content",
            "as": "a.png",
        }
        assert skipped["c_broken.png"]["reason"] == "invalid_image"

    scenario(tmp_path, monkeypatch, body)


def test_a_dataset_made_from_a_folder_says_what_in_it_is_no_image(
    tmp_path, monkeypatch
):
    # The 50 images' test 2026-10-29: a README and a folder in the folder were passed over
    # unsaid; asked what was not taken in, the reception said nothing was.
    from PIL import Image

    async def body(app, client, dataset, ids):
        folder = tmp_path / "made"
        (folder / "_meta").mkdir(parents=True)
        Image.new("RGB", (40, 30), (200, 10, 10)).save(folder / "a.png")
        (folder / "README.md").write_text("蝶", encoding="utf-8")
        args = {"name": "説明つき", "purpose": "試す", "paths": [str(folder)]}
        box = await client.post(
            "/v1/library/proposals",
            json={
                "agent": "reception",
                "tool": "dataset_create",
                "args": args,
                "title": "作る",
                "reason": "r",
            },
        )
        applied = (await client.post(f"/v1/proposals/{box.json()['id']}/apply")).json()
        skipped = {s["name"]: s["reason"] for s in applied["outcome"]["skipped"]}
        assert skipped == {"README.md": "invalid_image", "_meta": "folder"}

    scenario(tmp_path, monkeypatch, body)


def test_a_box_decided_in_a_later_chat_is_told_in_it(tmp_path, monkeypatch):
    # User 2026-10-29 (test S05): a box made in an earlier chat was decided in a later one; what
    # came of it and the run's end went to the earlier chat, where the person was not.
    async def body(app, client, dataset, ids):
        base = f"/v1/datasets/{dataset}"
        run = {
            "agent": "steward",
            "tool": "run_start",
            "args": {"image_ids": [ids["a.png"]]},
            "title": "流す",
            "reason": "r",
        }
        box = (await client.post(f"{base}/proposals", json=run)).json()
        here = (await client.post(f"{base}/agents/steward/chats", json={})).json()["id"]
        await client.post(f"{base}/agents/steward/chats", json={})  # the latest
        applied = await client.post(
            f"/v1/proposals/{box['id']}/apply", json={}, params={"chat": here}
        )
        await finished(client, applied.json()["outcome"]["id"])
        told = await client.get(f"{base}/agents/steward/events", params={"chat": here})
        assert {"box_applied", "run_ended"} <= {
            e["text"] for e in told.json()["events"]
        }

    scenario(tmp_path, monkeypatch, body)


def test_a_purpose_the_reception_guessed_is_changed_before_deciding(
    tmp_path, monkeypatch
):
    # The reception's tests 2026-10-29 (R01, R02): it wrote a purpose nobody said, fixed once the
    # dataset is made. User: "なおせるようにする": changed in the decision before deciding.
    from PIL import Image

    async def body(app, client, dataset, ids):
        folder = tmp_path / "made"
        folder.mkdir()
        Image.new("RGB", (40, 30), (200, 10, 10)).save(folder / "a.png")
        args = {"name": "箱", "purpose": "箱を囲む", "paths": [str(folder)]}
        box = await client.post(
            "/v1/library/proposals",
            json={
                "agent": "reception",
                "tool": "dataset_create",
                "args": args,
                "title": "作る",
                "reason": "r",
            },
        )
        applied = await client.post(
            f"/v1/proposals/{box.json()['id']}/apply",
            json={"args": {"purpose": "送り状を読む"}},
        )
        assert applied.status_code == 200, applied.text
        made = applied.json()
        assert made["changed"] == {"purpose": ["箱を囲む", "送り状を読む"]}
        found = await client.get(f"/v1/datasets/{made['outcome']['id']}")
        assert found.json()["purpose"] == "送り状を読む"

    scenario(tmp_path, monkeypatch, body)


def test_a_folder_not_there_is_refused_as_not_found(tmp_path, monkeypatch):
    # The reception's test 2026-10-29 (R06): a folder not there was refused as "no image file",
    # and the reception said so.
    async def body(app, client, dataset, ids):
        missing = str(tmp_path / "no_such_folder")
        box = await client.post(
            "/v1/library/proposals",
            json={
                "agent": "reception",
                "tool": "dataset_create",
                "args": {"name": "無い", "purpose": "試す", "paths": [missing]},
                "title": "作る",
                "reason": "r",
            },
        )
        error = box.json()["error"]
        assert error["message"] == "These paths are not found"
        assert error["details"]["paths"] == [missing]

    scenario(tmp_path, monkeypatch, body)
