"""The plan part (docs/2026-10-16-ontology-definition.md 11): a decision to run holds its plan
(a draft write or a version), model and effort by value, and that is what runs; what is decided
never differs from the plan (11.10: a later write withdraws a waiting box, no run is decided
while a worker answers)."""

from uuid import uuid4

from agent_app.errors import ApiError
from test_runs import DEFINITIONS, finished, save_version, scenario

from agent_app import runs as runs_module


def echoed(monkeypatch):
    """The CLIs' check as the run's own: the model and effort asked, else Sonnet at medium."""
    monkeypatch.setattr(
        runs_module,
        "selected_execution_settings",
        lambda model=None, effort=None, tier=None: {
            "model": model or "claude-sonnet-5-5",
            "effort": effort or "medium",
        },
    )


async def write(client, dataset, text, definitions=DEFINITIONS):
    found = await client.put(
        f"/v1/datasets/{dataset}/drafts/instruction",
        json={"text": text, "label_definitions": definitions},
    )
    assert found.status_code == 200, found.text
    return found.json()


async def box(client, dataset, image_ids, **args):
    made = await client.post(
        f"/v1/datasets/{dataset}/proposals",
        headers={"X-Actor": "ai"},
        json={
            "agent": "steward",
            "tool": "run_start",
            "args": {
                "image_ids": image_ids,
                "trial": True,
                "budget_per_image_usd": "1",
                **args,
            },
            "title": "試す",
            "reason": "r",
        },
    )
    assert made.status_code == 201, made.text
    return made.json()


async def version_text(client, dataset, revision):
    found = await client.get(f"/v1/datasets/{dataset}/instructions/{revision}")
    return found.json()["text"]


def test_an_approved_box_runs_the_write_it_holds_and_a_later_write_withdraws_it(
    tmp_path, monkeypatch
):
    # Review problem 2 (10-16): an approved box ran the draft as it was when the run started.
    # 10-17: what is decided never differs from the plan, so a later write withdraws the box.
    async def body(app, client, dataset, ids):
        echoed(monkeypatch)
        first = await write(client, dataset, "一つ目")
        made = await box(client, dataset, [ids["a.png"]])
        assert made["args"]["draft_write_id"] == first["write_id"]
        assert (made["args"]["model"], made["args"]["effort"]) == (
            "claude-opus-5-5",
            "medium",
        )
        assert made["preview"]["plan"]["next_revision"] == 2
        await write(client, dataset, "二つ目")
        old = (await client.get(f"/v1/proposals/{made['id']}")).json()
        assert old["state"] == "withdrawn"
        lines = (
            await client.get(f"/v1/datasets/{dataset}/agents/steward/events")
        ).json()["events"]
        assert any(e.get("text") == "box_withdrawn" for e in lines)
        again = await box(client, dataset, [ids["a.png"]])
        applied = await client.post(f"/v1/proposals/{again['id']}/apply", json={})
        assert applied.status_code == 200, applied.text
        run = await finished(client, applied.json()["outcome"]["id"])
        assert (
            await version_text(client, dataset, run["instruction_revision"]) == "二つ目"
        )
        # The box keeps the version it ran (its preview only foresaw one).
        assert applied.json()["outcome"]["revision"] == run["instruction_revision"]
        recipe = app.state.db.one(
            "SELECT * FROM recipes WHERE id=?", (run["recipe_id"],)
        )
        assert (recipe["instruction_revision"], recipe["model"], recipe["effort"]) == (
            run["instruction_revision"],
            "claude-opus-5-5",
            "medium",
        )
        # A box of a version points at what does not change: a write leaves it waiting.
        kept = await box(client, dataset, [ids["a.png"]], revision=2, trial=False)
        await write(client, dataset, "三つ目")
        assert (await client.get(f"/v1/proposals/{kept['id']}")).json()[
            "state"
        ] == "open"

    scenario(tmp_path, monkeypatch, body)


def test_a_persons_decision_runs_what_its_preview_showed_and_not_an_older_write(
    tmp_path, monkeypatch
):
    async def body(app, client, dataset, ids):
        echoed(monkeypatch)
        await write(client, dataset, "見た物")
        asked = {
            "tool": "run_start",
            "args": {"image_ids": [ids["a.png"]], "budget_per_image_usd": "1"},
            "title": "流す",
            "reason": "r",
        }
        base = f"/v1/datasets/{dataset}"
        seen = (await client.post(f"{base}/proposals/preview", json=asked)).json()
        await write(client, dataset, "後の物")
        refused = await client.post(
            f"{base}/decisions", json={**asked, "args": seen["args"]}
        )
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "plan_rewritten"
        seen = (await client.post(f"{base}/proposals/preview", json=asked)).json()
        done = await client.post(
            f"{base}/decisions", json={**asked, "args": seen["args"]}
        )
        assert done.status_code == 201, done.text
        run = await finished(client, done.json()["outcome"]["id"])
        assert (
            await version_text(client, dataset, run["instruction_revision"]) == "後の物"
        )

    scenario(tmp_path, monkeypatch, body)


def test_no_run_is_decided_while_a_worker_answers(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        echoed(monkeypatch)
        db = app.state.db
        await write(client, dataset, "答えの途中")
        made = await box(client, dataset, [ids["a.png"]])
        db.execute(
            "INSERT INTO jobs(id,dataset_id,agent,kind,state,title,created_at,bound_dataset_id)"
            " VALUES('job-t',?,'steward','answer_heavy','running','t','t',?)",
            (dataset, dataset),
        )
        agents = (await client.get(f"/v1/datasets/{dataset}/agents")).json()["agents"]
        assert {a["agent"]: a["answering"] for a in agents}["steward"] == 1
        refused = await client.post(f"/v1/proposals/{made['id']}/apply", json={})
        assert refused.json()["error"]["code"] == "workers_answering"
        own = await client.post(
            f"/v1/datasets/{dataset}/decisions",
            json={
                "tool": "run_start",
                "args": {"image_ids": [ids["a.png"]], "budget_per_image_usd": "1"},
                "title": "流す",
                "reason": "r",
            },
        )
        assert own.json()["error"]["code"] == "workers_answering"
        db.execute("UPDATE jobs SET state='done' WHERE id='job-t'")
        # The reception answering about the dataset (reading it) may write its plan too (48.10).
        db.execute(
            "INSERT INTO jobs(id,dataset_id,agent,kind,state,title,created_at,bound_dataset_id)"
            " VALUES('job-r',NULL,'reception','answer_heavy','queued','r','r',?)",
            (dataset,),
        )
        refused = await client.post(f"/v1/proposals/{made['id']}/apply", json={})
        assert refused.json()["error"]["code"] == "workers_answering"
        db.execute("UPDATE jobs SET state='done' WHERE id='job-r'")
        applied = await client.post(f"/v1/proposals/{made['id']}/apply", json={})
        assert applied.status_code == 200, applied.text
        await finished(client, applied.json()["outcome"]["id"])

    scenario(tmp_path, monkeypatch, body)


def test_a_box_says_what_it_runs_differently_from_the_way_last_run(
    tmp_path, monkeypatch
):
    async def body(app, client, dataset, ids):
        echoed(monkeypatch)
        base = f"/v1/datasets/{dataset}"
        first = await write(client, dataset, "確かめの印: 青")
        ran = await client.put(
            f"{base}/runs/{uuid4()}",
            json={"image_ids": [ids["a.png"]], "draft_write_id": first["write_id"]},
        )
        assert ran.status_code == 201, ran.text
        tried = await finished(client, ran.json()["id"])
        await write(client, dataset, "確かめの印: 赤")
        plan = (await box(client, dataset, [ids["a.png"]]))["preview"]["plan"]
        assert plan["against"] == {
            "revision": tried["instruction_revision"],
            "model": "claude-opus-5-5",
            "effort": "medium",
            "shared_revision": 1,
            "run_number": tried["number"],
        }
        assert plan["changes"]["text_added"] == ["確かめの印: 赤"]
        assert plan["changes"]["text_removed"] == ["確かめの印: 青"]
        assert not plan["same_way"]
        same = await box(
            client, dataset, [ids["a.png"]], revision=tried["instruction_revision"]
        )
        assert same["preview"]["plan"]["same_way"]
        # The record's way and what the plan says now differently.
        now_ = (await client.get(f"/v1/runs/{tried['id']}/plan-now")).json()
        assert now_["now"]["draft"] and now_["changes"]["text_added"] == [
            "確かめの印: 赤"
        ]

    scenario(tmp_path, monkeypatch, body)


def test_a_trial_and_the_run_after_it_are_one_version_and_one_way(
    tmp_path, monkeypatch
):
    async def body(app, client, dataset, ids):
        echoed(monkeypatch)
        written = await write(client, dataset, "試してから流す")
        base = f"/v1/datasets/{dataset}/runs"
        t1, r1, r2 = (str(uuid4()) for _ in range(3))
        trial = await client.put(
            f"{base}/{t1}",
            json={
                "image_ids": [ids["a.png"]],
                "trial": True,
                "draft_write_id": written["write_id"],
                "model": "claude-sonnet-5-5",
                "effort": "high",
            },
        )
        assert trial.status_code == 201, trial.text
        tried = await finished(client, t1)
        again = await client.put(
            f"{base}/{r1}",
            json={
                "revision": tried["instruction_revision"],
                "model": "claude-sonnet-5-5",
                "effort": "high",
            },
        )
        assert again.status_code == 201, again.text
        ran = await finished(client, r1)
        assert ran["recipe_id"] == tried["recipe_id"]
        # The same write again: the same version (no new one).
        once_more = await client.put(
            f"{base}/{r2}",
            json={
                "draft_write_id": written["write_id"],
                "model": "claude-sonnet-5-5",
                "effort": "high",
            },
        )
        assert once_more.status_code == 201, once_more.text
        assert (await finished(client, r2))["recipe_id"] == tried["recipe_id"]
        versions = (await client.get(f"/v1/datasets/{dataset}/instructions")).json()
        assert [v["revision"] for v in versions["instructions"]] == [2, 1]

    scenario(tmp_path, monkeypatch, body)


def test_a_workers_box_keeps_its_plan_and_a_person_may_change_its_model(
    tmp_path, monkeypatch
):
    # Definition 40.1 (user 2026-10-23): the model and the effort of a worker's box are the
    # person's to change, kept as changed; its plan stays (another plan is another box).
    async def body(app, client, dataset, ids):
        echoed(monkeypatch)
        await write(client, dataset, "箱の中身")
        made = await box(client, dataset, [ids["a.png"]])
        refused = await client.post(
            f"/v1/proposals/{made['id']}/apply", json={"args": {"revision": 1}}
        )
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "box_fixed"
        applied = await client.post(
            f"/v1/proposals/{made['id']}/apply",
            json={"args": {"model": "claude-haiku-5-5", "budget_per_image_usd": "2"}},
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["changed"]["model"] == [
            "claude-opus-5-5",
            "claude-haiku-5-5",
        ]
        run = await finished(client, applied.json()["outcome"]["id"])
        assert (run["settings"]["model"], run["budget_per_image_usd"]) == (
            "claude-haiku-5-5",
            "2",
        )

    scenario(tmp_path, monkeypatch, body)


def test_a_workers_new_run_withdraws_the_one_before(tmp_path, monkeypatch):
    # Definition 40.1: one waiting run of a kind, whose images the cards show.
    async def body(app, client, dataset, ids):
        await write(client, dataset, "箱の中身")
        first = await box(client, dataset, [ids["a.png"]])
        second = await box(client, dataset, [ids["fail.png"]])
        older = (await client.get(f"/v1/proposals/{first['id']}")).json()
        assert older["state"] == "withdrawn"
        assert older["outcome"]["cause"] == {"kind": "replaced", "by": second["id"]}

    scenario(tmp_path, monkeypatch, body)


def test_no_version_is_made_when_no_model_can_run(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        def unusable(*_args):
            raise ApiError(422, "no_ai_cli", "No usable AI CLI")

        monkeypatch.setattr(runs_module, "selected_execution_settings", unusable)
        written = await write(client, dataset, "流せない")
        refused = await client.put(
            f"/v1/datasets/{dataset}/runs/{uuid4()}",
            json={"image_ids": [ids["a.png"]], "draft_write_id": written["write_id"]},
        )
        assert refused.status_code == 422
        versions = (await client.get(f"/v1/datasets/{dataset}/instructions")).json()
        assert [v["revision"] for v in versions["instructions"]] == [1]
        draft = await client.get(f"/v1/datasets/{dataset}/drafts/instruction")
        assert draft.json()["write_id"] == written["write_id"]

    scenario(tmp_path, monkeypatch, body)


def test_a_waiting_box_reads_its_plan_as_it_is_now(tmp_path, monkeypatch):
    # Sol 2026-10-17: after a trial made version 2 of the same write, the waiting box still said
    # "kept as version 2 when it runs" (its preview was the one made with it).
    async def body(app, client, dataset, ids):
        echoed(monkeypatch)
        written = await write(client, dataset, "同じ書き込み")
        waiting = await box(client, dataset, [ids["fail.png"]])
        assert waiting["preview"]["plan"]["next_revision"] == 2
        ran = await client.put(
            f"/v1/datasets/{dataset}/runs/{uuid4()}",
            json={"image_ids": [ids["a.png"]], "draft_write_id": written["write_id"]},
        )
        await finished(client, ran.json()["id"])
        plan = (await client.get(f"/v1/proposals/{waiting['id']}")).json()["preview"][
            "plan"
        ]
        assert (plan["revision"], plan["next_revision"]) == (2, None)
        assert plan["same_way"] and plan["recipe"]["runs"] == 1

    scenario(tmp_path, monkeypatch, body)


def test_a_plan_back_to_an_earlier_version_runs_that_version(tmp_path, monkeypatch):
    # Issue #5-12 (review of 31abb2d): only the latest version was compared, so a plan
    # written back to version 1 and run made a new version the same as 1 (definition 1 D1).
    async def body(app, client, dataset, ids):
        echoed(monkeypatch)
        base = f"/v1/datasets/{dataset}/runs"
        first = (await write(client, dataset, "第一の本文"))["write_id"]
        one = await client.put(
            f"{base}/{uuid4()}",
            json={"image_ids": [ids["a.png"]], "trial": True, "draft_write_id": first},
        )
        await finished(client, one.json()["id"])
        second = (await write(client, dataset, "第二の本文"))["write_id"]
        two = await client.put(
            f"{base}/{uuid4()}",
            json={"image_ids": [ids["a.png"]], "trial": True, "draft_write_id": second},
        )
        await finished(client, two.json()["id"])
        back = (await write(client, dataset, "第一の本文"))["write_id"]
        shown = (await box(client, dataset, [ids["a.png"]], draft_write_id=back))[
            "preview"
        ]
        assert (shown["plan"]["revision"], shown["plan"]["next_revision"]) == (
            one.json()["instruction_revision"],
            None,
        )
        three = await client.put(
            f"{base}/{uuid4()}",
            json={"image_ids": [ids["a.png"]], "trial": True, "draft_write_id": back},
        )
        assert (
            three.json()["instruction_revision"] == one.json()["instruction_revision"]
        )

    scenario(tmp_path, monkeypatch, body)


def test_a_version_says_the_talk_of_the_box_that_made_it(tmp_path, monkeypatch):
    # 2026-10-30 (fact inventory 7, definition 58.4): a version's talk was looked for among the
    # boxes that saved a version, which are no more, so no version said where it was asked for.
    async def body(app, client, dataset, ids):
        echoed(monkeypatch)
        await write(client, dataset, "一つ目")
        made = await box(client, dataset, [ids["a.png"]])
        applied = await client.post(f"/v1/proposals/{made['id']}/apply", json={})
        assert applied.status_code == 200, applied.text
        run = await finished(client, applied.json()["outcome"]["id"])
        version = (
            await client.get(
                f"/v1/datasets/{dataset}/objects/version/{run['instruction_revision']}"
            )
        ).json()
        assert version["talk"] is not None, version
        assert (version["talk"]["agent"], version["talk"]["chat_id"]) == (
            "steward",
            made["chat_id"],
        )

    scenario(tmp_path, monkeypatch, body)


def test_a_version_says_what_it_leaves_out_differently_from_the_one_before(
    tmp_path, monkeypatch
):
    # 2026-10-30: the versions' list said a version changed only in its labels and text, so one
    # that took a reference or left something out was "nothing changed".
    async def body(app, client, dataset, ids):
        save_version(
            app.state.db,
            dataset,
            {
                "text": "円を囲む",
                "label_definitions": DEFINITIONS,
                "leave_out": ["欠けた円"],
            },
        )
        version = (await client.get(f"/v1/datasets/{dataset}/objects/version/2")).json()
        assert version["from_previous"]["leave_out"]["added"] == ["欠けた円"]

    scenario(tmp_path, monkeypatch, body)
