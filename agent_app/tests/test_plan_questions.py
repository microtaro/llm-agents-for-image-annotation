"""Questions with values (definition 26.4): the interview starts by itself on a plan with
nothing, an answer writes its option's plan as the person's own (refused when the plan changed
since it was asked), and what the person changes on the right is told to the plan worker."""

import asyncio
import json

from PIL import Image
from test_agents import fake_turns
from test_runs import DEFINITIONS, scenario

from agent_app import agent_answer

PERSON = {"X-Actor": "ui"}


def _option(label, plan=None, alias=None, start=None):
    return {
        "label": label,
        "recommend": False,
        "plan": plan,
        "alias": alias,
        "start": start,
    }


def _question(text, item, options):
    said = {"kind": "question", "message": "", "handoff": None}
    return {**said, "question": {"text": text, "item": item, "options": options}}


def _asked(db, dataset, question):
    """A worker's question line, its options checked as the answer path checks them: the
    options the server could not take."""
    from agent_app.agent_chat import add
    from agent_app.plan_questions import valued

    data, dropped = valued(db, dataset, question)
    add(db, dataset, "steward", "question", question["text"], data=data)
    return dropped


def test_an_answer_writes_its_option_as_the_persons_own(tmp_path, monkeypatch):
    async def body(app, client, _dataset, _ids):
        db = app.state.db
        # An image of no other dataset: nothing to choose from, the worker asks first (34.2).
        path = tmp_path / "new.png"
        Image.new("RGB", (240, 120), (90, 10, 10)).save(path)
        imported = await client.post("/v1/images/import", json={"paths": [str(path)]})
        dataset = (
            await client.post(
                "/v1/datasets",
                json={
                    "name": "聞き取り",
                    "purpose": "円",
                    "image_ids": [imported.json()["images"][0]["id"]],
                },
            )
        ).json()["id"]
        base = f"/v1/datasets/{dataset}"
        turns, told = [], []

        async def turn(
            self, job, text, looking, settings, session, record, again=False
        ):
            if again:
                # Told its option "読めない" is not a plan (68.2): it answers without it.
                told.append(text)
                labels = json.dumps({"label_definitions": DEFINITIONS})
                said = _question(
                    "何を囲みますか", "requirement", [_option("円を枠で", labels)]
                )
                return {**said, "boxes": [], "show": None}, None, None
            turns.append(text)
            if len(turns) == 1:
                labels = json.dumps({"label_definitions": DEFINITIONS})
                said = _question(
                    "何を囲みますか",
                    "requirement",
                    [_option("円を枠で", labels), _option("読めない", "{")],
                )
            elif len(turns) == 2:
                draft = json.loads(
                    db.one(
                        "SELECT payload_json FROM drafts WHERE dataset_id=?", (dataset,)
                    )["payload_json"]
                )
                circle = draft["label_definitions"][0]["id"]
                said = _question(
                    "付けない物はありますか",
                    "leave_out",
                    [
                        _option(
                            "影は付けない",
                            json.dumps({"leave_out": ["影"]}),
                            {"label_id": circle, "word": "まる"},
                        ),
                        _option("特に無し"),
                    ],
                )
            else:
                said = {"kind": "answer", "message": "書きました", "question": None}
                said = {**said, "handoff": None}
            return {**said, "boxes": [], "show": None}, None, None

        monkeypatch.setattr(agent_answer.Answers, "_turn", turn)
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "gpt-6.1-sol", "effort": "medium"},
        )

        async def settled():
            for _ in range(500):
                jobs = (await client.get("/v1/jobs")).json()
                if not jobs["running"] and not jobs["queued"]:
                    return
                await asyncio.sleep(0.01)

        async def lines():
            found = await client.get(f"{base}/agents/steward/events")
            return found.json()["events"]

        started = await client.post(f"{base}/plan/interview", headers=PERSON)
        assert started.json()["started"] is True
        again = await client.post(f"{base}/plan/interview", headers=PERSON)
        assert again.json()["started"] is False
        await settled()
        first = await lines()
        assert [e["data"]["note"] for e in first if e["kind"] == "note"] == [
            "interview"
        ]
        assert len(told) == 1 and "読めない" in told[0]
        asked = first[-1]
        assert [o["label"] for o in asked["data"]["options"]] == ["円を枠で"]
        # The person writes on the right twice: one line says what changed since before.
        for text in ("円", "円を囲む"):
            await client.put(
                f"{base}/drafts/instruction",
                json={"text": text, "label_definitions": DEFINITIONS},
                headers=PERSON,
            )
        right = [e for e in await lines() if (e["data"] or {}).get("note") == "right"]
        assert len(right) == 1 and right[0]["data"]["changes"]["added"] == ["circle"]
        # The plan changed since the question was asked: refused, nothing written.
        stale = await client.post(
            f"{base}/agents/steward/events/{asked['id']}/answer",
            json={"option": 0},
            headers=PERSON,
        )
        assert stale.json()["error"]["code"] == "question_stale"
        await client.post(
            f"{base}/agents/steward/messages",
            json={"text": "続けて"},
            headers=PERSON,
        )
        await settled()
        question = (await lines())[-1]
        assert question["data"]["premise"]["write_id"] is not None
        answered = await client.post(
            f"{base}/agents/steward/events/{question['id']}/answer",
            json={"option": 0},
            headers=PERSON,
        )
        assert answered.status_code == 202, answered.text
        await settled()
        draft = (await client.get(f"{base}/drafts/instruction")).json()
        assert (draft["leave_out"], draft["written_by"]) == (["影"], "person")
        state = (await client.get(f"{base}/plan/state")).json()
        assert {i["item"]: i["status"] for i in state["items"]}["leave_out"] == "person"
        said = await lines()
        assert [e["kind"] for e in said[-2:]] == ["human", "ai"]
        assert said[-2]["text"] == "影は付けない"
        # An answer is not a change on the right; the word the person chose finds the label.
        assert sum((e["data"] or {}).get("note") == "right" for e in said) == 1
        labels = (await client.get("/v1/labels")).json()["items"]
        assert [(i["name"], i["aliases"]) for i in labels] == [("circle", ["まる"])]
        twice = await client.post(
            f"{base}/agents/steward/events/{question['id']}/answer",
            json={"option": 0},
            headers=PERSON,
        )
        assert twice.json()["error"]["code"] == "question_closed"

    scenario(tmp_path, monkeypatch, body)


def test_a_trial_the_worker_proposed_wakes_it_when_it_ends(tmp_path, monkeypatch):
    # Found on the copy (10-20): the plan worker's trial ended and nobody asked whether its
    # results were right; definition 26.8 has the worker ask then.
    from test_runs import finished

    async def body(app, client, dataset, ids):
        woken = []

        async def turn(self, job, text, looking, settings, session, record):
            woken.append(
                self.db.one(
                    "SELECT data_json FROM agent_events WHERE id=?",
                    (job["request_event_id"],),
                )["data_json"]
            )
            said = {"kind": "answer", "message": "見ます", "question": None}
            return (
                {**said, "handoff": None, "boxes": [], "show": None},
                None,
                None,
            )

        monkeypatch.setattr(agent_answer.Answers, "_turn", turn)
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "gpt-6.1-sol", "effort": "medium"},
        )
        made = await client.post(
            f"/v1/datasets/{dataset}/proposals",
            json={
                "agent": "steward",
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
        box = made.json()
        applied = await client.post(f"/v1/proposals/{box['id']}/apply", headers=PERSON)
        assert applied.status_code == 200, applied.text
        run_id = applied.json()["outcome"]["id"]
        await finished(client, run_id)
        for _ in range(500):
            if woken:
                break
            await asyncio.sleep(0.01)
        assert json.loads(woken[0])["note"] == "run_ended"

    scenario(tmp_path, monkeypatch, body)


def test_an_option_starts_the_plan_again_from_blank(tmp_path, monkeypatch):
    # User 2026-10-22: asked to make the plan over, the worker offered "from blank", and the
    # server dropped it (an option held only a plan, and a plan with no label is refused).
    async def body(app, client, dataset, ids):
        db = app.state.db
        blank = _option(
            "白紙から始める",
            start={"kind": "blank", "dataset_id": None, "revision": None},
        )
        question = {"text": "どこから作り直しますか", "item": None, "options": [blank]}
        assert _asked(db, dataset, question) == []
        question = db.one("SELECT id FROM agent_events WHERE kind='question'")["id"]
        base = f"/v1/datasets/{dataset}"
        answered = await client.post(
            f"{base}/agents/steward/events/{question}/answer",
            json={"option": 0},
            headers=PERSON,
        )
        assert answered.status_code == 202, answered.text
        draft = (await client.get(f"{base}/drafts/instruction")).json()
        assert draft["label_definitions"] == [] and draft["from"]["kind"] == "blank"
        assert draft["written_by"] == "person"
        # Copy 2026-10-22: the plan blank, its state failed (compared with the versions as a
        # version's input, which has a label), and so did the worker's next answer; then every
        # item it emptied was the person's, and the next was the trial.
        state = await client.get(f"{base}/plan/state")
        assert state.status_code == 200, state.text
        assert state.json()["next"] == "requirement"

    scenario(tmp_path, monkeypatch, body)


def test_a_side_question_leaves_the_question_with_values_open(tmp_path, monkeypatch):
    # Astra 2026-10-20: asked "the cost?" before answering, the question closed, its options
    # went dim and it was never asked again.
    async def body(app, client, dataset, ids):
        db = app.state.db

        fake_turns(
            app,
            monkeypatch,
            lambda call: {"kind": "answer", "message": "1枚 約 $0.08 です"},
        )
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        labels = json.dumps({"label_definitions": DEFINITIONS})
        question = {
            "text": "どれ？",
            "item": "requirement",
            "options": [_option("円", labels)],
        }
        _asked(db, dataset, question)
        first = db.one("SELECT id FROM agent_events WHERE kind='question'")["id"]
        base = f"/v1/datasets/{dataset}/agents/steward"
        await client.post(f"{base}/messages", json={"text": "費用は？"}, headers=PERSON)
        for _ in range(500):
            if db.one("SELECT 1 FROM agent_events WHERE kind='ai'"):
                break
            await asyncio.sleep(0.01)
        open_ = "SELECT closed_at FROM agent_events WHERE id=?"
        assert db.one(open_, (first,))["closed_at"] is None
        _asked(db, dataset, {**question, "text": "次は？"})
        assert db.one(open_, (first,))["closed_at"] is not None

    scenario(tmp_path, monkeypatch, body)


def test_the_plan_entry_is_asked_by_the_server_and_wakes_the_worker_once(
    tmp_path, monkeypatch
):
    # User 2026-10-21: each question of a fixed form (how the plan is made, which existing plan,
    # as it is or changed) waited 20-85 s for the worker; the server asks them (34.2). These
    # images are in a dataset whose plan never ran: an existing plan too.
    async def body(app, client, dataset, ids):
        db = app.state.db
        new = (
            await client.post(
                "/v1/datasets",
                json={
                    "name": "円の写し",
                    "purpose": "円をもう一度",
                    "image_ids": list(ids.values()),
                },
            )
        ).json()["id"]
        base = f"/v1/datasets/{new}"
        started = await client.post(f"{base}/plan/interview", headers=PERSON)
        assert started.json() == {"started": True, "asked": "how"}
        jobs = "SELECT count(*) FROM jobs WHERE dataset_id=?"
        said = ("既存計画を使う", "1. 円（枠）", "既存計画 1 をそのまま使う")
        for step, words in zip(("how", "which", "keep"), said):
            question = db.one(
                "SELECT id, data_json FROM agent_events WHERE dataset_id=?"
                " AND kind='question' AND closed_at IS NULL",
                (new,),
            )
            assert json.loads(question["data_json"])["entry"]["step"] == step
            assert db.one(jobs, (new,))[0] == 0
            answered = await client.post(
                f"{base}/agents/steward/events/{question['id']}/answer",
                json={"option": 0, "words": words},
                headers=PERSON,
            )
            assert answered.status_code == 202, answered.text
        draft = (await client.get(f"{base}/drafts/instruction")).json()
        assert draft["from"]["dataset_id"] == dataset
        assert [d["name"] for d in draft["label_definitions"]] == [
            d["name"] for d in DEFINITIONS
        ]
        assert db.one(jobs, (new,))[0] == 1
        lines = db.execute(
            "SELECT text FROM agent_events WHERE dataset_id=? AND kind='human' ORDER BY id",
            (new,),
        )
        assert [r["text"] for r in lines] == list(said)

    scenario(tmp_path, monkeypatch, body)


def test_what_the_worker_says_before_its_question_is_shown_above_it(
    tmp_path, monkeypatch
):
    # 2026-10-29: asked 「8つの値ってなに？」, the worker named the eight values in its message
    # and asked again; only the question's line was written, so the person saw no answer.
    async def body(app, client, dataset, _ids):
        async def turn(self, job, text, looking, settings, session, record):
            said = _question("この8項目を読みますか", "requirement", [_option("はい")])
            said["message"] = "8項目は、ブランド・製品名・LOT・EXP などです。"
            return {**said, "boxes": [], "show": None}, None, None

        monkeypatch.setattr(agent_answer.Answers, "_turn", turn)
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "gpt-6.1-sol", "effort": "medium"},
        )
        base = f"/v1/datasets/{dataset}"
        await client.post(
            f"{base}/agents/steward/messages", json={"text": "8項目ってなに？"}
        )
        for _ in range(500):
            jobs = (await client.get("/v1/jobs")).json()
            if not jobs["running"] and not jobs["queued"]:
                break
            await asyncio.sleep(0.01)
        events = (await client.get(f"{base}/agents/steward/events")).json()["events"]
        said = [
            (e["kind"], e["text"]) for e in events if e["kind"] in ("ai", "question")
        ]
        assert said == [
            ("ai", "8項目は、ブランド・製品名・LOT・EXP などです。"),
            ("question", "この8項目を読みますか"),
        ]

    scenario(tmp_path, monkeypatch, body)
