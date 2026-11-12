"""The types of the things on the right and a worker's show (types design 2, 3)."""

import asyncio

import pytest
from test_agents import fake_turns
from test_runs import run_once, scenario

from agent_app import agent_answer


def test_a_set_is_read_by_its_types_conditions_within_the_dataset(
    tmp_path, monkeypatch
):
    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset)
        base = f"/v1/datasets/{dataset}/objects"
        ok = (await client.get(f"{base}/image?result=ok")).json()
        assert [i["image"]["id"] for i in ok["items"]] == [ids["a.png"]]
        failed = (await client.get(f"{base}/image?result=failed")).json()
        assert failed["count"] == 1
        # Stopped before it ended is not failed, as the screen's filters say (Astra 2026-10-20).
        with app.state.db.transaction():
            app.state.db.execute(
                "UPDATE results SET status='interrupted' WHERE image_id=?",
                (ids["fail.png"],),
            )
        failed = (await client.get(f"{base}/image?result=failed")).json()
        stopped = (await client.get(f"{base}/image?result=interrupted")).json()
        assert (failed["count"], stopped["count"]) == (0, 1)
        # By name, as the AI names images (the server finds the id).
        one = (await client.get(f"{base}/result?image=a.png")).json()
        assert one["count"] == 1 and one["items"][0]["image_id"] == ids["a.png"]
        # A field the type has not, and a record of another dataset, are refused.
        assert (await client.get(f"{base}/image?colour=red")).status_code == 422
        assert (await client.get(f"{base}/image?run=elsewhere")).status_code == 404

    scenario(tmp_path, monkeypatch, body)


def test_a_workers_show_is_checked_and_counted_on_its_line(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset)
        shows = iter(
            [
                {
                    "type": "result",
                    "id": None,
                    "where": [{"field": "image", "value": "a.png"}],
                    "title": "a の結果",
                },
                # User 2026-10-23: "（0枚）", three names joined in name (a part of one name).
                # Refused, the worker is asked again in the same conversation (41.1).
                {
                    "type": "image",
                    "id": None,
                    "where": [{"field": "name", "value": "a.png,fail.png"}],
                    "title": "2枚",
                },
                {
                    "type": "image",
                    "id": None,
                    "where": [{"field": "ids", "value": "a.png,fail.png"}],
                    "title": "2枚",
                },
            ]
        )

        calls = fake_turns(
            app,
            monkeypatch,
            lambda call: {"kind": "answer", "message": "ok", "show": next(shows)},
        )
        monkeypatch.setattr(
            agent_answer,
            "selected_execution_settings",
            lambda *_: {"model": "claude-haiku-5-5", "effort": "low"},
        )
        path = f"/v1/datasets/{dataset}/agents/steward"
        for text in ("a の結果を見せて", "2枚を見せて"):
            await client.post(f"{path}/messages", json={"text": text})
            for _ in range(500):
                jobs = (await client.get("/v1/jobs")).json()
                if not jobs["running"] and not jobs["queued"]:
                    break
                await asyncio.sleep(0.01)
        lines = [
            e
            for e in (await client.get(f"{path}/events")).json()["events"]
            if e["kind"] == "ai"
        ]
        assert lines[0]["data"]["show"] == {
            "type": "result",
            "id": None,
            "where": {"image": "a.png"},
            "count": 1,
            "title": "a の結果",
        }
        assert len(calls) == 3 and '"part": "show"' in calls[2]["message"]
        assert lines[1]["data"]["show"]["count"] == 2

    scenario(tmp_path, monkeypatch, body)


def test_a_types_buttons_and_a_workers_decisions_come_from_one_list(client):
    # Types design 8, definition 22.2 (issue #5-8: the decisions were listed in two places):
    # the screen's buttons, the decisions a proposal may hold and the decision tools all come
    # from actions.DECISIONS.
    import typing

    from agent_app.actions import DECISIONS
    from agent_app.mcp_general import GENERAL, ProposalIn
    from agent_app.proposals import Tool

    types = client.get("/v1/object-types").json()
    run = {a["name"]: a for a in types["run"]["actions"]}
    assert run["stop"]["path"] == "/v1/runs/{id}/stop"
    assert set(run) == {"stop", "use"}
    buttons = {
        a["decision_tool"]
        for actions in (t["actions"] for t in types.values())
        for a in actions
        if a["decision_tool"]
    }
    assert buttons <= set(DECISIONS)
    assert set(typing.get_args(Tool)) == set(DECISIONS)
    proposed = ProposalIn.model_json_schema()["properties"]["tool"]["enum"]
    assert set(proposed) == set(DECISIONS)
    assert {n for n, t in GENERAL.items() if t.kind == "decision"} == set(DECISIONS)


def test_a_show_of_one_record_counts_its_images(tmp_path, monkeypatch):
    # User 2026-10-23: "記録 1の見本（1件）" read as one sample while the record had three
    # images; the count is of what the right shows (definition 39.1).
    from agent_app.object_types import check_show

    async def body(app, client, dataset, ids):
        run = await run_once(client, app, dataset)
        db = app.state.db
        one = check_show(db, dataset, {"type": "run", "id": run["id"], "where": []})
        every = check_show(db, dataset, {"type": "run", "id": None, "where": []})
        assert (one["count"], every["count"]) == (2, 1)

    scenario(tmp_path, monkeypatch, body)


def test_a_show_of_a_label_no_dataset_annotated_is_refused(tmp_path, monkeypatch):
    # User 2026-10-27: "同じ物か" showed a library label as 0 objects beside the images; the
    # right shows a label's objects, so a label with none is a show of nothing (definition 41.1).
    from agent_app.errors import ApiError
    from agent_app.object_types import check_show

    async def body(app, client, dataset, ids):
        db = app.state.db
        label = next(x for x in (await client.get("/v1/labels")).json()["items"])
        show = {"type": "label", "id": label["id"], "where": []}
        with pytest.raises(ApiError) as refused:
            check_show(db, dataset, show)
        assert refused.value.code == "show_empty"
        await run_once(client, app, dataset)
        assert check_show(db, dataset, show)["count"] == 1

    scenario(tmp_path, monkeypatch, body)


def test_one_image_or_result_shown_says_where_it_opens(tmp_path, monkeypatch):
    # 2026-10-28: an image given by its name as the id was counted as one, but the line kept the
    # name and the right, comparing ids, showed nothing; one image or result opens large, by its
    # image (and a result's record) the server found (definition 59.2).
    from agent_app.object_types import check_show

    async def body(app, client, dataset, ids):
        run = await run_once(client, app, dataset)
        db = app.state.db
        image = check_show(db, dataset, {"type": "image", "id": "a.png", "where": []})
        assert (image["id"], image["image_id"]) == (ids["a.png"], ids["a.png"])
        named = [{"field": "ids", "value": "a.png"}]
        listed = check_show(db, dataset, {"type": "image", "id": None, "where": named})
        assert (listed["id"], listed["where"].get("ids")) == (ids["a.png"], None)
        row = db.one(
            "SELECT id, image_id FROM results WHERE run_id=? AND image_id=?",
            (run["id"], ids["a.png"]),
        )
        result = check_show(
            db, dataset, {"type": "result", "id": row["id"], "where": []}
        )
        assert result["image_id"] == row["image_id"]
        assert result["record"] == {
            "id": run["id"],
            "trial": False,
            "revision": run["instruction_revision"],
        }

    scenario(tmp_path, monkeypatch, body)
