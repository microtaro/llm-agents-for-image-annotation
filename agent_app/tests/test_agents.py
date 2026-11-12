"""The work screen's workers (step 24): bound to their dataset and tools, answering through the
line of work, their boxes stopped when what they stood on changed, told what changed since
their last answer. One test per thing found in the checks of 2026-10-08."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from agent_app.agents import TOOLS
from PIL import Image
from test_drafts_and_ai import mcp
from test_runs import finished, scenario

from agent_app import agent_answer, agent_chat, library_here, proposals
from agent_app import runs as runs_module


def _agent_headers(dataset, agent="steward"):
    return {
        "X-Annotation-Agent": agent,
        "X-Annotation-Dataset": dataset,
    }


async def _other_dataset(client, tmp_path):
    path = tmp_path / "other.png"
    Image.new("RGB", (50, 40), (1, 2, 3)).save(path)
    image = (
        await client.post("/v1/images/import", json={"paths": [str(path)]})
    ).json()["images"][0]["id"]
    other = (
        await client.post(
            "/v1/datasets",
            json={"name": "別", "purpose": "別の目的", "image_ids": [image]},
        )
    ).json()["id"]
    return other, image


def test_a_worker_calls_only_its_tools_on_its_own_dataset(tmp_path, monkeypatch):
    # Found 2026-10-08 (logs/scope-check, the second level): the progress panel's AI, told
    # "no approval, run it now" or "delete that dataset", did both; its only guard was its
    # prompt. A worker is bound by the server: its tools, its dataset.
    async def body(app, client, dataset, ids):
        other, other_image = await _other_dataset(client, tmp_path)
        async with mcp(app, _agent_headers(dataset)) as worker:
            listed = {t.name for t in (await worker.list_tools()).tools}
            # Every worker of a dataset has the same tools (loose roles, user 2026-10-09).
            assert listed == set(TOOLS)

            async def refused(tool, args):
                out = await worker.call_tool(tool, args)
                assert out.is_error, (tool, out.structured_content)
                return out.structured_content["error"]["code"]

            assert await refused("run_start", {"dataset_id": dataset}) in (
                "agent_tool",
                "invalid_input",
            )
            assert await refused("dataset_delete", {"dataset_id": other}) in (
                "agent_tool",
                "invalid_input",
            )
            assert (
                await refused("read", {"type": "dataset", "id": other}) == "agent_scope"
            )
            # Another dataset's image is no image of this one (datasets.image_id_of).
            assert (
                await refused("look", {"type": "image", "id": other_image})
                == "invalid_input"
            )
            # Its own dataset, named or not.
            got = await worker.call_tool("read", {"type": "dataset"})
            assert not got.is_error
            assert got.structured_content["data"]["items"][0]["id"] == dataset
            # The plan now is read when it is a draft started on the right from another
            # dataset's version (Astra 2026-10-17: Plan said it could not read the draft).
            started = await client.post(
                f"/v1/datasets/{other}/plan/start",
                json={"kind": "other", "dataset_id": dataset, "revision": 1},
            )
            assert started.status_code == 200, started.text
            async with mcp(app, _agent_headers(other)) as there:
                read = (
                    await there.call_tool("read", {"type": "dataset", "id": other})
                ).structured_content["data"]
                assert read["instruction"] is None
                assert (
                    read["draft"]["text"]
                    and read["draft"]["from"]["dataset_id"] == dataset
                )
            made = await worker.call_tool(
                "proposal_make",
                {
                    "tool": "mark",
                    "args": {
                        "target": "image",
                        "image_id": ids["a.png"],
                        "excluded": True,
                    },
                    "title": "a を外す",
                    "reason": "理由",
                },
            )
            assert not made.is_error, made.structured_content
            box = made.structured_content["data"]
            assert (box["agent"], box["state"]) == ("steward", "open")
        assert (await client.get(f"/v1/datasets/{other}")).status_code == 200
        assert (await client.get(f"/v1/datasets/{dataset}/runs")).json()["runs"] == []
        # The manual app's AI (no worker headers) keeps every tool, as before.
        async with mcp(app) as person:
            everything = {t.name for t in (await person.list_tools()).tools}
            assert {
                "run_start",
                "dataset_delete",
            } <= everything and "sql_query" not in everything

    scenario(tmp_path, monkeypatch, body)


def test_a_worker_sees_how_to_propose_and_a_mistake_says_what_to_fix(
    tmp_path, monkeypatch
):
    # Issue #3 (review of 31abb2d): a wrong argument of a proposal came back as a broken write,
    # "never blindly resend" (U-01); a worker saw no shape of a proposal's arguments (U-02); an
    # image named by its name, as the prompt says, was "not of this dataset" (U-06); a refusal
    # said no other way (U-07).
    async def body(app, client, dataset, ids):
        async with mcp(app, _agent_headers(dataset)) as worker:
            tools = {t.name: t for t in (await worker.list_tools()).tools}
            shape = json.dumps(tools["proposal_make"].input_schema)
            assert "budget_per_image_usd" in shape and "excluded" in shape
            wrong = (
                await worker.call_tool(
                    "proposal_make",
                    {
                        "tool": "run_start",
                        # A limit is not needed (the settings' then); the old name of
                        # all the images' limit is no argument (definition 65).
                        "args": {
                            "image_ids": ["a.png"],
                            "trial": True,
                            "budget_usd": "1",
                        },
                        "title": "a を試す",
                        "reason": "r",
                    },
                )
            ).structured_content
            assert (wrong["error"]["code"], wrong["save_status"]) == (
                "invalid_input",
                "not_attempted",
            )
            assert "Fix the arguments" in wrong["next_actions"][0]
            made = (
                await worker.call_tool(
                    "proposal_make",
                    {
                        "tool": "run_start",
                        "args": {
                            "image_ids": ["a.png"],
                            "trial": True,
                            "budget_per_image_usd": "1",
                        },
                        "title": "a を試す",
                        "reason": "r",
                    },
                )
            ).structured_content
            assert made["ok"], made
            assert made["data"]["args"]["image_ids"] == [ids["a.png"]]
            direct = (
                await worker.call_tool(
                    "run_start",
                    {"image_ids": [ids["a.png"]], "budget_per_image_usd": "1"},
                )
            ).structured_content
            assert direct["error"]["code"] == "agent_tool"
            assert "proposal_make(tool=run_start" in direct["next_actions"][0]

    scenario(tmp_path, monkeypatch, body)


def test_runs_wait_in_the_line_and_the_same_image_is_refused(tmp_path, monkeypatch):
    # Before step 24 a second run was refused (409 run_busy); the checks of 2026-10-08
    # (logs/parallel-check) ran two and four at once as fast as one.
    async def body(app, client, dataset, ids):
        release = asyncio.Event()
        real = runs_module.infer

        async def held(*args):
            await release.wait()
            return await real(*args)

        monkeypatch.setattr(runs_module, "infer", held)
        await client.put("/v1/settings", json={"run_slots": 1})
        first, second, third = (str(uuid4()) for _ in range(3))
        base = f"/v1/datasets/{dataset}/runs"
        one = await client.put(f"{base}/{first}", json={"image_ids": [ids["a.png"]]})
        two = await client.put(
            f"{base}/{second}", json={"image_ids": [ids["fail.png"]]}
        )
        assert (one.status_code, two.status_code) == (201, 201)
        jobs = (await client.get("/v1/jobs", params={"dataset": dataset})).json()
        waiting = [j for j in jobs["jobs"] if j["state"] == "queued"]
        assert [(j["run_id"], j["wait_reason"]) for j in waiting] == [(second, "slots")]
        await client.put("/v1/settings", json={"run_slots": 2})
        app.state.jobs.kick()
        # The same image again while a decided run holds it: refused when it is decided
        # (user 2026-10-17: waiting in the line, it replaced the earlier result unseen; it
        # waited for "same_images" since 10-08). A run waiting in the line holds it too.
        three = await client.put(
            f"{base}/{third}", json={"image_ids": [ids["fail.png"]]}
        )
        assert (three.status_code, three.json()["error"]["code"]) == (
            409,
            "images_writing",
        )
        assert [i["name"] for i in three.json()["error"]["details"]["images"]] == [
            "fail.png"
        ]
        release.set()
        for run_id in (first, second):
            assert (await finished(client, run_id))["status"] in ("succeeded", "failed")
        # Every end reaches its worker's conversation (never a silent end).
        events = (
            await client.get(f"/v1/datasets/{dataset}/agents/steward/events")
        ).json()["events"]
        ended = [e["data"]["run_id"] for e in events if e["text"] == "run_ended"]
        assert sorted(ended) == sorted([first, second])

    scenario(tmp_path, monkeypatch, body)


def test_a_box_is_withdrawn_when_what_it_stood_on_changed(tmp_path, monkeypatch):
    # The notify check of 2026-10-08: a change during an answer did not reach that answer;
    # the box it made stood on the old data. Changed values are applied once and recorded.
    # Since 2026-10-17 (definition 18.13) the box is withdrawn with what changed, not stopped.
    async def body(app, client, dataset, ids):
        base = f"/v1/datasets/{dataset}/proposals"
        mark = {
            "agent": "steward",
            "tool": "mark",
            "args": {"target": "image", "image_id": ids["a.png"], "excluded": True},
            "title": "a を外す",
            "reason": "r",
        }
        box = (await client.post(base, json=mark)).json()
        assert box["preview"]["excluded_now"] is False
        await client.post(f"/v1/datasets/{dataset}/images/{ids['a.png']}/exclude")
        # Withdrawn by that write, before anyone reads it (issue #5-4, definition 19.7).
        found = app.state.db.one("SELECT state FROM proposals WHERE id=?", (box["id"],))
        assert found["state"] == "withdrawn"
        refused = await client.post(f"/v1/proposals/{box['id']}/apply")
        assert (refused.status_code, refused.json()["error"]["code"]) == (
            409,
            "proposal_decided",
        )
        withdrawn = (await client.get(f"/v1/proposals/{box['id']}")).json()
        assert (withdrawn["state"], withdrawn["outcome"]["cause"]) == (
            "withdrawn",
            {"kind": "done", "image": "a.png"},
        )
        # Withdrawn is not a trouble of the worker (definition 11.10).
        agents = (await client.get(f"/v1/datasets/{dataset}/agents")).json()["agents"]
        assert next(a for a in agents if a["agent"] == "steward")["trouble"] == 0

        mark = {
            "agent": "steward",
            "tool": "mark",
            "args": {"target": "image", "image_id": ids["a.png"], "excluded": True},
            "title": "a を外す",
            "reason": "r",
        }
        box = (await client.post(base, json=mark)).json()
        applied = await client.post(
            f"/v1/proposals/{box['id']}/apply", json={"args": {"excluded": False}}
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["changed"] == {"excluded": [True, False]}
        events = (
            await client.get(f"/v1/datasets/{dataset}/agents/steward/events")
        ).json()["events"]
        assert events[-1]["data"]["changed"] == {"excluded": [True, False]}

    scenario(tmp_path, monkeypatch, body)


def test_a_waiting_run_is_withdrawn_when_its_image_was_run_first(tmp_path, monkeypatch):
    # User 2026-10-17: Plan's "try A006" waited while the person tried A006 on the right; the
    # box then asked for a remake, though A006 was done. The first decided wins: the waiting
    # box is withdrawn and says which record went first.
    async def body(app, client, dataset, ids):
        box = (
            await client.post(
                f"/v1/datasets/{dataset}/proposals",
                json={
                    "agent": "steward",
                    "tool": "run_start",
                    "args": {"image_ids": [ids["a.png"]], "budget_per_image_usd": "1"},
                    "title": "a を試す",
                    "reason": "r",
                },
            )
        ).json()
        run_id = str(uuid4())
        await client.put(
            f"/v1/datasets/{dataset}/runs/{run_id}", json={"image_ids": [ids["a.png"]]}
        )
        await finished(client, run_id)
        seen = (await client.get(f"/v1/proposals/{box['id']}")).json()
        # Withdrawn when record 1 was decided (definition 19.7), while it was going.
        assert (seen["state"], seen["outcome"]["cause"]) == (
            "withdrawn",
            {
                "kind": "results",
                "images": [{"name": "a.png", "record_number": 1, "going": True}],
            },
        )

    scenario(tmp_path, monkeypatch, body)


def test_a_persons_same_decision_is_theirs_and_withdraws_the_box(tmp_path, monkeypatch):
    # User 2026-10-17: a person's run on the right, by chance the same as a worker's waiting
    # box, approved that box. The person's decision is theirs; the box is withdrawn.
    async def body(app, client, dataset, ids):
        run = {
            "tool": "run_start",
            "args": {"image_ids": [ids["a.png"]], "budget_per_image_usd": "1"},
            "title": "a を試す",
            "reason": "r",
        }
        base = f"/v1/datasets/{dataset}"
        box = (
            await client.post(f"{base}/proposals", json={**run, "agent": "steward"})
        ).json()
        own = (
            await client.post(f"{base}/decisions", json=run, headers={"X-Actor": "ui"})
        ).json()
        # Issue #4 F-04, #5-13 (definition 21.3): a person's own press is a decision with no
        # proposal, told in the place's chat; a box's decision names the box and its worker.
        assert (own["proposal_id"], own["decided_by"], own["requested_by"]) == (
            None,
            "person",
            "person",
        )
        assert app.state.db.one("SELECT count(*) FROM proposals")[0] == 1
        await finished(client, own["outcome"]["id"])
        seen = (await client.get(f"/v1/proposals/{box['id']}")).json()
        assert seen["state"] == "withdrawn"
        made = (await client.get(f"/v1/runs/{own['outcome']['id']}")).json()
        assert made["decision"]["id"] == own["id"]
        lines = (await client.get(f"{base}/agents/steward/events")).json()["events"]
        assert own["id"] in [(e["data"] or {}).get("decision_id") for e in lines]
        again = (
            await client.post(
                f"{base}/proposals",
                json={**run, "agent": "steward"},
                headers=_agent_headers(dataset),
            )
        ).json()
        applied = await client.post(
            f"/v1/proposals/{again['id']}/apply", headers={"X-Actor": "ui"}
        )
        assert applied.status_code == 200, applied.text
        await finished(client, applied.json()["outcome"]["id"])
        made = (await client.get(f"/v1/runs/{applied.json()['outcome']['id']}")).json()
        assert {
            k: made["decision"][k]
            for k in ("proposal_id", "decided_by", "requested_by")
        } == {
            "proposal_id": again["id"],
            "decided_by": "person",
            "requested_by": "agent:steward",
        }

    scenario(tmp_path, monkeypatch, body)


def fake_turns(app, monkeypatch, answer):
    """The chats' kept CLIs faked (residents.Residents.turn): answer(call) gives each turn's
    answer; the calls are kept, each with its key, model, context and message."""
    calls = []

    async def turn(key, **given):
        calls.append({"key": key, **given})
        said = {"question": None, "handoff": None, "boxes": []}
        return {**said, "show": None, **answer(calls[-1])}, None, {"session_id": "s"}

    monkeypatch.setattr(app.state.jobs.residents, "turn", turn)
    return calls


def test_an_answer_a_person_stops_is_a_note_and_its_question_opens_again(
    tmp_path, monkeypatch
):
    # User 2026-10-23: a stopped answer showed "could not answer" with a button to see to it
    # (definition 41.2), and its question stayed answered though nothing came of it (41.3).
    async def body(app, client, dataset, ids):
        never = asyncio.Event()
        asked = {
            "kind": "question",
            "message": "どうしますか",
            "question": {
                "text": "どうしますか",
                "item": None,
                "options": [
                    {
                        "label": "位置",
                        "recommend": True,
                        "plan": None,
                        "alias": None,
                        "start": None,
                    }
                ],
            },
            "handoff": None,
            "boxes": [],
            "show": None,
        }
        turns = []

        async def turn(key, **given):
            turns.append(given)
            if len(turns) == 1:
                return asked, None, {"session_id": "s"}
            await never.wait()

        monkeypatch.setattr(app.state.jobs.residents, "turn", turn)
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-opus-5-5", "effort": "medium"},
        )
        path = f"/v1/datasets/{dataset}/agents/steward"

        async def going():
            for _ in range(500):
                jobs = (await client.get("/v1/jobs")).json()
                running = [j for j in jobs["jobs"] if j["state"] == "running"]
                if running or not (jobs["running"] or jobs["queued"]):
                    return running
                await asyncio.sleep(0.01)
            return []

        await client.post(f"{path}/messages", json={"text": "考えて"})
        await going()
        while (await client.get("/v1/jobs")).json()["running"]:
            await asyncio.sleep(0.01)
        question = next(
            e
            for e in (await client.get(f"{path}/events")).json()["events"]
            if e["kind"] == "question"
        )
        pressed = await client.post(
            f"{path}/events/{question['id']}/answer", json={"option": 0}
        )
        assert pressed.status_code == 202, pressed.text
        running = await going()
        stopped = await client.post(f"/v1/jobs/{running[0]['id']}/cancel", json={})
        assert stopped.status_code == 200, stopped.text
        while (await client.get("/v1/jobs")).json()["running"]:
            await asyncio.sleep(0.01)
        events = (await client.get(f"{path}/events")).json()["events"]
        assert (events[-1]["kind"], events[-1]["text"]) == ("note", "answer_cancelled")
        again = next(e for e in events if e["id"] == question["id"])
        assert again["closed_at"] is None and "answered" not in again["data"]
        steward = next(
            a
            for a in (await client.get(f"/v1/datasets/{dataset}/agents")).json()[
                "agents"
            ]
            if a["agent"] == "steward"
        )
        assert steward["trouble"] == 0
        # The app closing stops it: said as the app stopped, to ask again, not as a person's
        # stop (2026-10-29: a restart said "stopped answering" as if the person had stopped
        # it; definition 72), and its question opens again too.
        pressed = await client.post(
            f"{path}/events/{question['id']}/answer", json={"option": 0}
        )
        assert pressed.status_code == 202, pressed.text
        await going()
        await app.state.jobs.close()
        events = (await client.get(f"{path}/events")).json()["events"]
        assert (events[-1]["kind"], events[-1]["data"]["code"]) == (
            "failed",
            "app_stopped",
        )
        again = next(e for e in events if e["id"] == question["id"])
        assert again["closed_at"] is None

    scenario(tmp_path, monkeypatch, body)


def test_a_persons_line_goes_to_the_workers_own_conversation(tmp_path, monkeypatch):
    # Definition 28 (user 2026-10-20): a quick answer of a fast model read every line first;
    # it passed 7 of 10 on, their time lost, and answered some it was asked to look at.
    # Every line goes to the chat's kept conversation of the worker's model, with what
    # changed since its last answer.
    async def body(app, client, dataset, ids):
        await client.put("/v1/settings", json={"agent_model": "claude-opus-5-5"})
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda model=None, effort=None, tier=None: {
                "model": model,
                "effort": effort or "medium",
            },
        )
        answers = iter(
            [
                {"kind": "answer", "message": "a を見ました"},
                {"kind": "answer", "message": "どういたしまして"},
            ]
        )
        calls = fake_turns(app, monkeypatch, lambda call: next(answers))
        path = f"/v1/datasets/{dataset}/agents/steward"
        for text in ("a を見て", "ありがとう"):
            asked = (await client.post(f"{path}/messages", json={"text": text})).json()
            for _ in range(500):
                job = (await client.get(f"/v1/jobs/{asked['job_id']}")).json()
                if job["state"] not in ("queued", "running"):
                    break
                await asyncio.sleep(0.01)
        assert [(c["settings"]["model"], c["message"]) for c in calls] == [
            ("claude-opus-5-5", "a を見て"),
            ("claude-opus-5-5", "ありがとう"),
        ]
        assert len({c["key"] for c in calls}) == 1
        assert "changes" in calls[0]["context"]
        lines = (await client.get(f"{path}/events")).json()["events"]
        assert [(e["text"], e["model"]) for e in lines if e["kind"] == "ai"] == [
            ("a を見ました", "claude-opus-5-5"),
            ("どういたしまして", "claude-opus-5-5"),
        ]

    scenario(tmp_path, monkeypatch, body)


def test_a_steward_hands_the_librarys_request_to_the_reception(tmp_path, monkeypatch):
    # Definition 36.7 (user 2026-10-22: "clicked, and nothing went to the reception"): asked
    # for a new dataset, the steward only pointed to the reception (a nudge) and the request
    # was lost. Asked for, it goes into a new chat of the reception at once, which answers it.
    async def body(app, client, dataset, ids):
        def answer(call):
            if call["headers"]["X-Annotation-Agent"] == "steward":
                offer = {
                    "agent": "reception",
                    "summary": "円と同じ画像で新しいデータセットを作る",
                    "now": True,
                }
                return {
                    "kind": "handoff",
                    "message": "受付に伝えました",
                    "handoff": offer,
                }
            return {"kind": "answer", "message": "作る決定を用意しました", "open": None}

        calls = fake_turns(app, monkeypatch, answer)
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-opus-5-5", "effort": "medium"},
        )
        path = f"/v1/datasets/{dataset}/agents/steward"
        await client.post(
            f"{path}/messages", json={"text": "新しいデータセットを作って"}
        )
        for _ in range(500):
            if len(calls) == 2:
                break
            await asyncio.sleep(0.01)
        mine = (await client.get(f"{path}/events")).json()["events"]
        assert [(e["kind"], e["closed_at"] is not None) for e in mine[1:]] == [
            ("handoff_offer", True),
            ("note", False),
        ]
        assert mine[-1]["data"]["to_agent"] == "reception"
        # The reception read it with the dataset it came from on the right.
        assert calls[1]["context"]["here"]["dataset_id"] == dataset
        theirs = (await client.get("/v1/library/agents/reception/events")).json()[
            "events"
        ]
        assert (theirs[0]["by"], theirs[0]["text"]) == (
            "agent:steward",
            "円と同じ画像で新しいデータセットを作る",
        )

    scenario(tmp_path, monkeypatch, body)


def test_answers_with_tools_use_the_workers_model_never_haiku(tmp_path, monkeypatch):
    # Found 2026-10-08: the answers with tools took the last run's model, so after a run on
    # Haiku 5.5 they were Haiku's too. User: "Haiku cannot do the heavy ones."
    async def body(app, client, dataset, ids):
        refused = await client.put(
            "/v1/settings", json={"agent_model": "claude-haiku-5-5"}
        )
        assert (refused.status_code, refused.json()["error"]["code"]) == (
            422,
            "light_model",
        )
        chosen = []

        def selected(model=None, effort=None, tier=None):
            chosen.append((model, effort))
            return {"model": model or "gpt-6.1-sol", "effort": effort or "medium"}

        async def turn(self, job, text, looking, settings, session, record):
            return (
                {"kind": "answer", "message": "ok", "question": None, "handoff": None},
                None,
                None,
            )

        monkeypatch.setattr(agent_answer, "selected_execution_settings", selected)
        monkeypatch.setattr(agent_answer.Answers, "_turn", turn)
        with app.state.db.transaction():
            app.state.db.execute(
                "INSERT INTO runs(id,dataset_id,status,instruction_revision,requirement_key,"
                "requested_json,worker_prompt,worker_prompt_sha256,settings_json,request_json,"
                "budget_per_image_usd,started_at,number) VALUES('r-haiku',?,'succeeded',1,'k','[]','p',"
                "'s','{\"model\": \"claude-haiku-5-5\"}','{}','1','2026-10-08T00:00:00Z',99)",
                (dataset,),
            )
        event = agent_chat.add(
            app.state.db, dataset, "steward", "human", "考えて", "ui"
        )
        job = app.state.jobs.enqueue(dataset, "steward", "answer_heavy", "t", event)
        for _ in range(500):
            if app.state.jobs.get(job["id"])["state"] not in ("queued", "running"):
                break
            await asyncio.sleep(0.01)
        assert chosen == [("claude-opus-5-5", "medium")]

    scenario(tmp_path, monkeypatch, body)


def test_a_box_changed_by_hand_is_stopped_before_it_is_applied(tmp_path, monkeypatch):
    # Sol's work screen audit 2026-10-08: after a person left the image out by hand, the box
    # still waited and showed the image as in; it stopped only when applied.
    async def body(app, client, dataset, ids):
        base = f"/v1/datasets/{dataset}/proposals"
        mark = {
            "agent": "steward",
            "tool": "mark",
            "args": {"target": "image", "image_id": ids["a.png"], "excluded": True},
            "title": "a を外す",
            "reason": "r",
        }
        box = (await client.post(base, json=mark)).json()
        await client.post(f"/v1/datasets/{dataset}/images/{ids['a.png']}/exclude")
        seen = (await client.get(f"/v1/proposals/{box['id']}")).json()
        assert seen["state"] == "withdrawn"
        assert seen["outcome"]["now"]["excluded_now"] is True
        agents = (await client.get(f"/v1/datasets/{dataset}/agents")).json()["agents"]
        production = next(a for a in agents if a["agent"] == "steward")
        assert (production["boxes"], production["trouble"]) == (0, 0)
        # Two readers withdrawing it at once tell the worker once (the screen showed two lines).
        row = app.state.db.one("SELECT * FROM proposals WHERE id=?", (box["id"],))
        proposals._withdraw_changed(app.state.db, row, ({}, {}), "server")
        told = agent_chat.changes_since(app.state.db, dataset, "steward")
        assert [n["note"] for n in told] == ["box_withdrawn"]

    scenario(tmp_path, monkeypatch, body)


def test_the_reception_is_told_what_waits_for_the_person(tmp_path, monkeypatch):
    # Sol's audit: asked where the person's things wait, the reception said the boxes were
    # not in what it was shown.
    async def body(app, client, dataset, ids):
        mark = {
            "agent": "steward",
            "tool": "mark",
            "args": {"target": "image", "image_id": ids["a.png"], "excluded": True},
            "title": "a を外す",
            "reason": "r",
        }
        await client.post(f"/v1/datasets/{dataset}/proposals", json=mark)
        found = library_here.library_context(app.state.db, {"dataset_id": dataset})
        assert found["here"]["turns"]["steward"]["boxes"] == 1
        assert found["datasets"][0]["turns"]["steward"]["boxes"] == 1

    scenario(tmp_path, monkeypatch, body)


def test_heavy_answers_wait_only_within_one_chat(tmp_path, monkeypatch):
    # 10-13: the memory is the chat's since 10-09 evening, but a heavy answer of another chat
    # of the same worker waited too (the wait was left per worker).
    async def body(app, client, dataset, ids):
        release = asyncio.Event()

        async def held(job):
            await release.wait()

        app.state.jobs.runners["answer_heavy"] = held
        db = app.state.db
        one, other = (agent_chat.new_chat(db, dataset, "steward") for _ in range(2))
        # All three waiting before the line is looked at once: the first of a chat started in
        # that same look holds the next of the chat (found 2026-10-13: it was noted per worker).
        kick = app.state.jobs.kick
        app.state.jobs.kick = lambda: None
        jobs = [
            app.state.jobs.enqueue(
                dataset,
                "steward",
                "answer_heavy",
                "t",
                agent_chat.add(
                    db, dataset, "steward", "human", "考えて", "ui", chat_id=chat
                ),
            )
            for chat in (one, one, other)
        ]
        app.state.jobs.kick = kick
        kick()
        await asyncio.sleep(0.05)
        states = [
            (
                app.state.jobs.get(j["id"])["state"],
                app.state.jobs.get(j["id"])["wait_reason"],
            )
            for j in jobs
        ]
        assert states == [
            ("running", None),
            ("queued", "same_agent"),
            ("running", None),
        ]
        release.set()

    scenario(tmp_path, monkeypatch, body)


def test_answers_with_tools_do_not_wait_for_runs(tmp_path, monkeypatch):
    # 2026-10-20: runs and answers with tools shared the heavy slots, so two runs going held
    # every answer with tools; a person talks while runs go (definition 27.6).
    async def body(app, client, dataset, ids):
        release = asyncio.Event()

        async def held(job):
            await release.wait()

        jobs = app.state.jobs
        jobs.runners["run"] = jobs.runners["answer_heavy"] = held
        await client.put("/v1/settings", json={"run_slots": 1})
        runs = [jobs.enqueue(dataset, None, "run", "t", run_id=f"r{n}") for n in (1, 2)]
        asked = agent_chat.add(
            app.state.db, dataset, "steward", "human", "考えて", "ui"
        )
        answer = jobs.enqueue(dataset, "steward", "answer_heavy", "t", asked)
        await asyncio.sleep(0.05)
        states = [jobs.get(j["id"])["state"] for j in [*runs, answer]]
        assert states == ["running", "queued", "running"]
        release.set()

    scenario(tmp_path, monkeypatch, body)


def test_one_press_applies_a_box_and_defaults_and_stuck_runs_are_one(
    tmp_path, monkeypatch
):
    # Issue #5 (review of 31abb2d): two presses at once both ran a box (1); a box, a preview
    # and a run of nothing chosen took different models, and a Haiku run became the default
    # (10, user 2026-10-09: Haiku is chosen, never the default); a queued run with no job was
    # never started nor ended, and now it would hold its images' lock for ever (11).
    from agent_app.image_state import writing
    from agent_app.run_inputs import default_choice

    async def body(app, client, dataset, ids):
        db = app.state.db
        made = (
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
        assert proposals._take(db, made["id"])
        again = await client.post(f"/v1/proposals/{made['id']}/apply")
        assert (again.status_code, again.json()["error"]["code"]) == (
            409,
            "proposal_decided",
        )

        monkeypatch.setattr(
            runs_module,
            "selected_execution_settings",
            lambda model=None, effort=None, tier=None: {
                "model": model or "claude-sonnet-5-5",
                "effort": effort or "medium",
            },
        )
        haiku = str(uuid4())
        await client.put(
            f"/v1/datasets/{dataset}/runs/{haiku}",
            json={"image_ids": [ids["a.png"]], "model": "claude-haiku-5-5"},
        )
        await finished(client, haiku)
        assert default_choice(db)[0] == "claude-opus-5-5"
        # The default is the settings', not the dataset's last run's (user 2026-10-27).
        put = await client.put(
            "/v1/settings",
            json={"run_model": "claude-sonnet-5-5", "run_effort": "high"},
        )
        assert put.status_code == 200
        assert default_choice(db)[:2] == ("claude-sonnet-5-5", "high")
        refused = await client.put(
            "/v1/settings", json={"run_model": "claude-haiku-5-5"}
        )
        assert refused.json()["error"]["code"] == "light_model"

        with db.transaction():
            db.execute("UPDATE runs SET status='queued' WHERE id=?", (haiku,))
            db.execute("UPDATE results SET status='pending' WHERE run_id=?", (haiku,))
        assert writing(db, dataset, [ids["a.png"]])
        runs_module.Runs(db)  # the server started again
        assert (
            db.one("SELECT status FROM runs WHERE id=?", (haiku,))[0] == "interrupted"
        )
        assert writing(db, dataset, [ids["a.png"]]) == []

    scenario(tmp_path, monkeypatch, body)


def test_who_did_it_is_said_in_one_word(tmp_path, monkeypatch):
    # Issue #4 F-02 (definition 21.2): who did a thing was ui/ai/api/server, a worker's name
    # and a model's, and a fix with no header was "api". One word now: person, agent:<worker>,
    # server, outside.
    async def body(app, client, dataset, ids):
        db = app.state.db
        mark = {
            "tool": "mark",
            "args": {"target": "image", "image_id": ids["a.png"], "excluded": True},
            "title": "a を使わない",
            "reason": "r",
        }
        base = f"/v1/datasets/{dataset}/proposals"
        box = (
            await client.post(base, json=mark, headers=_agent_headers(dataset))
        ).json()
        assert box["made_by"] == "agent:steward"
        run_id = str(uuid4())
        await client.put(
            f"/v1/datasets/{dataset}/runs/{run_id}", json={"image_ids": [ids["a.png"]]}
        )
        await finished(client, run_id)
        assert (
            db.one(
                "SELECT d.decided_by FROM runs r JOIN decisions d ON d.id=r.decision_id"
                " WHERE r.id=?",
                (run_id,),
            )[0]
            == "outside"
        )
        # The run moved what the box stood on: the server withdrew it.
        withdrawn = (await client.get(f"/v1/proposals/{box['id']}")).json()
        assert (withdrawn["state"], withdrawn["decided_by"]) == ("withdrawn", "server")

    scenario(tmp_path, monkeypatch, body)


def test_an_id_does_not_move_a_tool_to_another_place(tmp_path, monkeypatch):
    # Review 2026-10-28 (C#1): look(type="label", id="../datasets/B") read another dataset's
    # sheet: the id went into the path as it was, and the HTTP client resolved "..".
    async def body(app, client, dataset, ids):
        other, _ = await _other_dataset(client, tmp_path)
        async with mcp(app, _agent_headers(dataset)) as worker:
            out = await worker.call_tool(
                "look", {"type": "label", "id": f"../datasets/{other}"}
            )
            assert out.is_error, out.structured_content
            assert out.structured_content["error"]["code"] == "invalid_input"

    scenario(tmp_path, monkeypatch, body)


def test_a_part_of_an_answer_the_server_cannot_use_is_asked_again_then_said(
    tmp_path, monkeypatch
):
    # 2026-10-29, swept after 「8つの値ってなに？」: a question given with kind=answer was
    # dropped without a word, and the worker never knew. The worker is told why and answers
    # again once; what it still gives that cannot be used is said to the person (68.2).
    async def body(app, client, dataset, ids):
        asked = {
            "text": "どれにしますか",
            "item": None,
            "options": [
                {
                    "label": "位置",
                    "recommend": True,
                    "plan": None,
                    "alias": None,
                    "start": None,
                }
            ],
        }
        calls = fake_turns(
            app,
            monkeypatch,
            lambda call: {"kind": "answer", "message": "見ました", "question": asked},
        )
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        path = f"/v1/datasets/{dataset}/agents/steward"
        await client.post(f"{path}/messages", json={"text": "見て"})
        for _ in range(500):
            jobs = (await client.get("/v1/jobs")).json()
            if not jobs["running"] and not jobs["queued"]:
                break
            await asyncio.sleep(0.01)
        assert len(calls) == 2 and '"part": "question"' in calls[1]["message"]
        lines = (await client.get(f"{path}/events")).json()["events"]
        assert [e["kind"] for e in lines][-2:] == ["ai", "note"]
        assert lines[-2]["text"] == "見ました"
        assert [p["part"] for p in lines[-1]["data"]["parts"]] == ["question"]

    scenario(tmp_path, monkeypatch, body)


def test_every_worker_takes_a_request_not_of_this_app_the_same_way():
    # 2026-10-29: asked about the weather, code and a ramen shop, the steward wrote code and the
    # reception declined as "the reception": no rule said (definition 69).
    from agent_app.agents import NOT_HERE_WORDS
    from agent_app.screen_words import LANGUAGE

    for role in agent_answer.ROLES.values():
        assert NOT_HERE_WORDS in role.rules
        # Answered in the language the person wrote in (2026-10-29: English on a Japanese
        # screen got Japanese; definition 75).
        assert LANGUAGE in role.rules
        assert not [
            m for m in ("{not_here}", "{lines}", "{language}") if m in role.rules
        ]


def test_every_worker_reads_the_settings_and_none_changes_them(tmp_path, monkeypatch):
    # User 2026-10-29: asked the model and the cost limit, the steward could answer only from a
    # waiting decision, and the reception said where the data is kept was not to be seen; the
    # settings are a type read like the others, with the screen's words and what each does,
    # read only (definition 71).
    async def body(app, client, dataset, ids):
        for agent, where in (("reception", None), ("steward", dataset)):
            headers = {"X-Annotation-Agent": agent, "X-Annotation-Dataset": where or ""}
            async with mcp(app, headers) as worker:
                out = await worker.call_tool("read", {"type": "settings"})
                assert not out.is_error, out.structured_content
                items = out.structured_content["data"]["items"]
                # Nothing a worker calls changes them: no tool, no decision.
                names = {t.name for t in (await worker.list_tools()).tools}
                assert not [n for n in names if "setting" in n]
            slots = next(i for i in items if i["key"] == "run_slots")
            assert slots["screen"]["ja"] and slots["range"] == [1, 8]
            assert {i["key"] for i in items if i["group"] == "machine"} == {
                "version",
                "free_memory_mb",
                "storage",
            }
            # What each does is the screen's own tip, in both languages (definition 72).
            assert all(i["does"]["ja"] and i["does"]["en"] for i in items)
        from agent_app.actions import DECISIONS

        assert not [d for d in DECISIONS if "setting" in d]

    scenario(tmp_path, monkeypatch, body)


def test_a_dataset_named_with_another_ones_name_is_said_again(tmp_path, monkeypatch):
    # 2026-10-29: the reception wrote "#34「確かめ 段ボール」", #34 being 確かめ 順番 (the names
    # began alike), and the person read it as it was. The worker is told the right name and
    # answers again (definition 73).
    async def body(app, client, dataset, ids):
        found = (await client.get(f"/v1/datasets/{dataset}")).json()
        number, name = found["number"], found["name"]
        said = iter(
            [
                f"#{number}「別の名前」が待っています",
                f"#{number}「{name}」が待っています",
            ]
        )
        calls = fake_turns(
            app, monkeypatch, lambda call: {"kind": "answer", "message": next(said)}
        )
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        path = f"/v1/datasets/{dataset}/agents/steward"
        await client.post(f"{path}/messages", json={"text": "何が待ってる？"})
        for _ in range(500):
            jobs = (await client.get("/v1/jobs")).json()
            if not jobs["running"] and not jobs["queued"]:
                break
            await asyncio.sleep(0.01)
        assert len(calls) == 2 and f"「{name}」" in calls[1]["message"]
        lines = (await client.get(f"{path}/events")).json()["events"]
        assert lines[-1]["text"] == f"#{number}「{name}」が待っています"

    scenario(tmp_path, monkeypatch, body)


def test_what_the_person_already_said_is_not_asked_again():
    # 2026-11-05: a dataset made to outline each animal got a question recommending boxes.
    rules = (
        Path(agent_answer.__file__).with_name("agent_prompt.yaml").read_text("utf-8")
    )
    assert "What the person already said" in rules
    assert "the option that says what they said is the recommended one" in rules


def test_the_check_of_every_answer_finds_words_that_did_not_reach_the_person(
    tmp_path, monkeypatch
):
    # 2026-10-29: the tests read the screen only, and 89 of 89 questions lost the words before
    # them. The answer as the worker gave it is kept, and a check by machine finds what of it
    # is on no line (definition 74).
    import sqlite3
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools/ui_audit"))
    import invariants

    async def body(app, client, dataset, ids):
        option = {"label": "位置", "recommend": True, "plan": None, "alias": None}
        fake_turns(
            app,
            monkeypatch,
            lambda call: {
                "kind": "question",
                "message": "4枚とも箱が1つです",
                "question": {
                    "text": "何を読みますか",
                    "item": None,
                    "options": [{**option, "start": None}],
                },
            },
        )
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        await client.post(
            f"/v1/datasets/{dataset}/agents/steward/messages", json={"text": "見て"}
        )
        for _ in range(500):
            jobs = (await client.get("/v1/jobs")).json()
            if not jobs["running"] and not jobs["queued"]:
                break
            await asyncio.sleep(0.01)
        db = sqlite3.connect(app.state.db.path)
        db.row_factory = sqlite3.Row
        job = db.execute("SELECT * FROM jobs WHERE kind='answer_heavy'").fetchone()
        assert (
            json.loads(job["said_json"])[0]["said"]["message"] == "4枚とも箱が1つです"
        )
        assert invariants.check_answer(db, job) == []
        # The words before the question lost, as before 10-29: found.
        db.execute("DELETE FROM agent_events WHERE text='4枚とも箱が1つです'")
        assert [rule for rule, _ in invariants.check_answer(db, job)] == ["I1"]

    scenario(tmp_path, monkeypatch, body)


def test_a_worker_is_told_the_persons_time_to_say_times_in(tmp_path, monkeypatch):
    # 2026-10-29 (the workers' tests S05, S06): one answer said a record's time in the person's
    # time, another as UTC, as it read it (definition 74).
    import re

    from agent_app.screen_words import TIMES

    async def body(app, client, dataset, ids):
        calls = fake_turns(
            app, monkeypatch, lambda call: {"kind": "answer", "message": "はい"}
        )
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        await client.post(
            f"/v1/datasets/{dataset}/agents/steward/messages", json={"text": "いつ？"}
        )
        for _ in range(500):
            jobs = (await client.get("/v1/jobs")).json()
            if not jobs["running"] and not jobs["queued"]:
                break
            await asyncio.sleep(0.01)
        assert re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d[+-]\d\d:\d\d", calls[0]["context"]["now"]
        )
        assert TIMES in calls[0]["rules"]

    scenario(tmp_path, monkeypatch, body)


def test_the_steward_knows_its_datasets_number(tmp_path, monkeypatch):
    # 2026-10-29 (S12): "#29 の画像を流して" was read as an image named #29; the steward knew
    # its dataset's name only (definition 75).
    async def body(app, client, dataset, ids):
        number = (await client.get(f"/v1/datasets/{dataset}")).json()["number"]
        assert (
            agent_answer.dataset_context(app.state.db, dataset, "steward")["number"]
            == number
        )
        assert "#number「name」" in agent_answer.ROLES["steward"].rules

    scenario(tmp_path, monkeypatch, body)


def test_an_answer_given_again_keeps_its_cost():
    # 2026-10-29: the reception's answer given again had no cost: the two turns' cache writes
    # were added, but their breakdown by retention was the second turn's alone.
    from agent_app.agent_answer import added
    from agent_app.costs import api_cost
    from agent_app.model_catalog import CLAUDE_PRICE_VERSION

    turn = {
        "input_tokens": 10,
        "output_tokens": 20,
        "cached_input_tokens": 30,
        "cache_write_input_tokens": 40,
        "raw": {"ephemeral_5m_input_tokens": 40, "ephemeral_1h_input_tokens": 0},
        "inclusion": {
            "cached_input_tokens": "external",
            "cache_write_input_tokens": "external",
        },
    }
    settings = {
        "model": "claude-opus-5-5",
        "tier": "standard",
        "api_price_version": CLAUDE_PRICE_VERSION,
        "usd_to_jpy": "160",
    }
    once, twice = api_cost(turn, settings), api_cost(added(turn, turn), settings)
    assert twice["missing_reason"] is None
    assert float(twice["usd"]) == 2 * float(once["usd"])


def test_a_workers_cost_limit_and_a_purpose_it_writes_are_the_persons_to_see():
    # The 50 images' test 2026-10-29: the steward gave Astra's samples a limit from Sonnet's
    # costs and three of five stopped; the reception wrote purposes nobody said (R01, R02).
    from agent_app.mcp_general import RunStartIn

    limit = RunStartIn.model_fields["budget_per_image_usd"].description
    assert "Give it only when the person gave one" in limit
    assert "only the one the person gave" in agent_answer.ROLES["steward"].rules
    assert "it is your guess" in agent_answer.ROLES["reception"].rules


def test_every_worker_tells_a_version_from_a_draft_and_counts_as_it_offers():
    # The workers' tests 2026-10-29: a draft called 今の計画書, "3 existing plans" offered as two,
    # a cost of no model named, "a trouble to see", a folder not found said as a maybe.
    from agent_app.screen_words import SAYING

    for role in agent_answer.ROLES.values():
        assert SAYING in role.rules
        assert "下書き / draft; say which" in role.rules
        assert "never a trouble" in role.rules
        assert "never 参考例" in role.rules and "never 「」" in role.rules
