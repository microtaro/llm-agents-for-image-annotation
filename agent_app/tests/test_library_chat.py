"""The library's reception (types design 16.2): it answers from the library's summaries, and
a request it offers to hand over goes into the dataset worker's own chat once a person agrees."""

import asyncio
import json

from test_agents import fake_turns
from test_runs import scenario

from agent_app import agent_answer


def test_the_library_reception_answers_and_hands_a_request_to_a_dataset_worker(
    tmp_path, monkeypatch
):
    async def body(app, client, dataset, ids):
        offer = {
            "dataset_id": dataset,
            "agent": "steward",
            "summary": "採用の様子を見せて",
        }
        calls = fake_turns(
            app,
            monkeypatch,
            lambda call: {
                "kind": "handoff",
                "message": "円の採用を実施・採用係に回しますか？",
                "open": None,
                "handoff": offer,
            },
        )
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        asked = await client.post(
            "/v1/library/agents/reception/messages", json={"text": "円の採用を見たい"}
        )
        assert asked.status_code == 202, asked.text
        for _ in range(500):
            got = (await client.get("/v1/library/agents/reception/events")).json()
            if not got["answering"]:
                break
            await asyncio.sleep(0.01)
        offer = got["events"][-1]
        assert (offer["kind"], offer["data"]["agent"]) == (
            "handoff_offer",
            "steward",
        )
        # It read the library's summary of the dataset, by name.
        assert "円を囲む" in json.dumps(calls[0]["context"], ensure_ascii=False)
        handed = await client.post(
            "/v1/library/agents/reception/handoffs", json={"event_id": offer["id"]}
        )
        assert handed.status_code == 202, handed.text
        talk = (
            await client.get(f"/v1/datasets/{dataset}/agents/steward/events")
        ).json()["events"]
        assert talk[0]["text"] == "採用の様子を見せて"
        assert talk[0]["data"]["from_agent"] == "reception"
        # The worker knows its dataset by the name the request used (Sol 2026-10-12).
        found = agent_answer.dataset_context(app.state.db, dataset, "steward")
        assert found["dataset"] == "円"
        again = await client.post(
            "/v1/library/agents/reception/handoffs", json={"event_id": offer["id"]}
        )
        assert again.status_code == 409

    scenario(tmp_path, monkeypatch, body)


def test_a_request_the_person_asked_for_goes_to_the_worker_at_once(
    tmp_path, monkeypatch
):
    # User 2026-10-22: having chosen "remake the plan (計画)" in the reception's question, the
    # reception only pointed at the plan and the person had to say it again to the plan worker.
    async def body(app, client, dataset, ids):
        offer = {
            "dataset_id": dataset,
            "agent": "steward",
            "summary": "計画書を最初から作り直したい",
            "now": True,
        }
        fake_turns(
            app,
            monkeypatch,
            lambda call: {
                "kind": "handoff",
                "message": "計画係に伝えました。",
                "open": None,
                "handoff": offer,
            },
        )
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        await client.post(
            "/v1/library/agents/reception/messages", json={"text": "計画書から作り直す"}
        )
        for _ in range(500):
            got = (await client.get("/v1/library/agents/reception/events")).json()
            if got["events"][-1]["kind"] == "note":
                break
            await asyncio.sleep(0.01)
        line, note = got["events"][-2:]
        assert line["kind"] == "handoff_offer" and line["closed_at"] is not None
        assert (note["data"]["note"], note["data"]["to_agent"]) == (
            "handed",
            "steward",
        )
        talk = (
            await client.get(f"/v1/datasets/{dataset}/agents/steward/events")
        ).json()["events"]
        assert talk[0]["text"] == "計画書を最初から作り直したい"

    scenario(tmp_path, monkeypatch, body)


def test_the_reception_reads_the_dataset_on_the_right_and_opens_an_image_by_name(
    tmp_path, monkeypatch
):
    """One reception (16.2a): it reads the dataset the right shows, and an image it names
    opens by the image's id, which the server finds."""

    async def body(app, client, dataset, ids):
        images = (await client.get(f"/v1/datasets/{dataset}")).json()["images"]
        name = images[1]["name"]
        place = {
            "dataset_id": dataset,
            "stage": "production",
            "image": name,
            "now": True,
        }
        calls = fake_turns(
            app,
            monkeypatch,
            lambda call: {
                "kind": "open",
                "message": f"{name} を出します。",
                "open": place,
            },
        )
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        asked = await client.post(
            "/v1/library/agents/reception/messages",
            json={
                "text": f"{name} を見せて",
                "looking_at": {"dataset_id": dataset, "stage": "instruction"},
            },
        )
        assert asked.status_code == 202, asked.text
        for _ in range(500):
            got = (await client.get("/v1/library/agents/reception/events")).json()
            if not got["answering"]:
                break
            await asyncio.sleep(0.01)
        opened = got["events"][-1]
        assert opened["kind"] == "open"
        assert opened["data"] == {
            "dataset_id": dataset,
            "stage": "production",
            "now": True,
            "image_id": images[1]["image_id"],
            "image_name": name,
            "proposal_ids": [],
        }
        # It read the dataset on the right: where in it, and its images by name.
        here = calls[0]["context"]["here"]
        assert here["dataset_id"] == dataset and name in json.dumps(
            here, ensure_ascii=False
        )

    scenario(tmp_path, monkeypatch, body)


def test_a_run_keeps_the_draft_as_a_version_and_each_write_is_recorded(
    tmp_path, monkeypatch
):
    """User 2026-10-15 (types design 20.1): no saving by hand. A trial may be made with a draft
    open; the box holds the draft's write, and the run makes the next version of it (the same
    content as the latest version adds none; definition 11.2). Every write of the draft is
    kept, and a version's plan can be written back as the draft."""
    from agent_app.drafts import draft_write_id, version_from_write

    async def body(app, client, dataset, ids):
        db = app.state.db
        base = f"/v1/datasets/{dataset}/drafts/instruction"
        latest = (
            await client.get(f"/v1/datasets/{dataset}/instructions/latest")
        ).json()
        drafted = await client.put(
            base,
            json={"text": "直し中", "label_definitions": latest["label_definitions"]},
        )
        assert drafted.status_code < 300, drafted.text
        made = await client.post(
            f"/v1/datasets/{dataset}/proposals",
            json={
                "agent": "steward",
                "tool": "run_start",
                "args": {
                    "image_ids": list(ids.values())[:1],
                    "trial": True,
                    "budget_per_image_usd": "1",
                },
                "title": "1枚を試す",
                "reason": "r",
            },
        )
        assert made.status_code == 201, made.text
        write = made.json()["args"]["draft_write_id"]
        assert write == drafted.json()["write_id"]
        assert version_from_write(db, dataset, write, "ui", None) == 2
        assert (await client.get(base)).json() is None
        back = await client.post(base + "/from-version", json={"revision": 1})
        assert back.json()["text"] == latest["text"]
        await client.post(base + "/from-version", json={"revision": 2})
        # Back to the latest: no draft, which reads as none (not a 404, user 2026-10-27).
        assert (await client.get(base)).json() is None
        assert draft_write_id(db, dataset) is None
        versions = (await client.get(f"/v1/datasets/{dataset}/instructions")).json()
        assert [v["revision"] for v in versions["instructions"]] == [2, 1]
        diff = (await client.get(f"/v1/datasets/{dataset}/instructions/2/diff")).json()
        assert diff["revision"] == 1 and diff["text_changed"]
        writes = db.execute(
            "SELECT written_by FROM draft_writes WHERE dataset_id=?", (dataset,)
        )
        assert len(writes) == 2

    scenario(tmp_path, monkeypatch, body)


def test_a_reception_answer_a_person_stops_says_so(tmp_path, monkeypatch):
    # User 2026-10-23: the reception's answer spun for half a minute and there was no way to
    # stop it; stopped, it is said as a worker's is (definition 45).
    async def body(app, client, dataset, ids):
        never = asyncio.Event()

        async def turn(key, **given):
            await never.wait()

        monkeypatch.setattr(app.state.jobs.residents, "turn", turn)
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-opus-5-5", "effort": "medium"},
        )
        asked = await client.post(
            "/v1/library/agents/reception/messages", json={"text": "何種類？"}
        )
        job = asked.json()["job_id"]
        for _ in range(500):
            if (await client.get(f"/v1/jobs/{job}")).json()["state"] == "running":
                break
            await asyncio.sleep(0.01)
        stopped = await client.post(f"/v1/jobs/{job}/cancel", json={})
        assert stopped.status_code == 200, stopped.text
        for _ in range(500):
            got = (await client.get("/v1/library/agents/reception/events")).json()
            if not got["answering"]:
                break
            await asyncio.sleep(0.01)
        last = got["events"][-1]
        assert (last["kind"], last["data"]["note"]) == ("note", "answer_cancelled")

    scenario(tmp_path, monkeypatch, body)


def test_the_steward_and_the_reception_say_what_they_are_doing(tmp_path, monkeypatch):
    # User 2026-10-24: while a worker answered, the talk showed only that it thought; what it
    # is doing (the tool going) is the job's, for every worker alike (definition 48.7).
    async def body(app, client, dataset, ids):
        going, release = asyncio.Event(), asyncio.Event()

        async def turn(key, **given):
            record = given["record"]
            call = {"type": "mcp_tool_call", "id": "c1", "tool": "dataset_sheet"}
            await record(
                {"type": "item.started", "item": {**call, "arguments": {"page": 2}}}
            )
            going.set()
            await release.wait()
            await record(
                {"type": "item.completed", "item": {**call, "status": "completed"}}
            )
            said = {"question": None, "handoff": None, "open": None, "boxes": []}
            return {**said, "kind": "answer", "message": "10種類"}, None, {}

        monkeypatch.setattr(app.state.jobs.residents, "turn", turn)
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-opus-5-5", "effort": "medium"},
        )
        asked = await client.post(
            "/v1/library/agents/reception/messages", json={"text": "何種類？"}
        )
        job = asked.json()["job_id"]
        await asyncio.wait_for(going.wait(), 5)
        doing = (await client.get(f"/v1/jobs/{job}")).json()["doing"]
        assert doing == {
            "going": [{"tool": "dataset_sheet", "args": {"page": 2}}],
            "done": [],
        }
        release.set()
        for _ in range(500):
            got = (await client.get("/v1/library/agents/reception/events")).json()
            if not got["answering"]:
                break
            await asyncio.sleep(0.01)
        assert (await client.get(f"/v1/jobs/{job}")).json()["doing"] is None
        # The library's workers, as a dataset's: the reception's newest line for its mark.
        library = (await client.get("/v1/library/agents")).json()["agents"]
        reception = next(a for a in library if a["agent"] == "reception")
        assert reception["last_event"] == got["events"][-1]["id"]

    scenario(tmp_path, monkeypatch, body)


def test_a_trial_the_reception_proposed_wakes_it_in_the_library(tmp_path, monkeypatch):
    # Definition 48.12: the reception may do a dataset's work when asked (the roles are loose);
    # its trial's end woke it at the dataset, so its own talk showed no answer going.
    from test_runs import finished

    async def body(app, client, dataset, ids):
        woken = []

        async def turn(self, job, text, looking, settings, session, record):
            woken.append(dict(job))
            said = {"kind": "answer", "message": "見ます", "question": None}
            return ({**said, "handoff": None, "boxes": [], "open": None}, None, None)

        monkeypatch.setattr(agent_answer.Answers, "_turn", turn)
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "gpt-6.1-sol", "effort": "medium"},
        )
        made = await client.post(
            f"/v1/datasets/{dataset}/proposals",
            json={
                "agent": "reception",
                "tool": "run_start",
                "args": {
                    "trial": True,
                    "image_ids": [ids["a.png"]],
                    "budget_per_image_usd": "1",
                },
                "title": "a で試す",
                "reason": "r",
            },
        )
        assert made.status_code in (200, 201), made.text
        applied = await client.post(
            f"/v1/proposals/{made.json()['id']}/apply", headers={"X-Actor": "ui"}
        )
        assert applied.status_code == 200, applied.text
        await finished(client, applied.json()["outcome"]["id"])
        for _ in range(500):
            if woken:
                break
            await asyncio.sleep(0.01)
        # In the library (its talk's place), bound to the dataset it tried.
        assert (woken[0]["dataset_id"], woken[0]["bound_dataset_id"]) == (None, dataset)

    scenario(tmp_path, monkeypatch, body)
