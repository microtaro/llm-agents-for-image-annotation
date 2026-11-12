"""The person's turns: counted everywhere and cleared at once (definition 44)."""

from test_runs import scenario

from agent_app import agent_chat


def test_the_persons_turns_clear_in_one_place_or_everywhere(tmp_path, monkeypatch):
    # User 2026-10-23: "as long as this number is there I'm not at ease", "there is no way to
    # clear this request": a question could not be closed, and the reception's number left out
    # the other datasets and the library.
    async def body(app, client, dataset, ids):
        db = app.state.db
        mark = {
            "agent": "steward",
            "tool": "mark",
            "args": {"target": "image", "image_id": ids["a.png"], "excluded": True},
            "title": "a を外す",
            "reason": "r",
        }
        made = await client.post(f"/v1/datasets/{dataset}/proposals", json=mark)
        assert made.status_code == 201, made.text
        options = {"options": [{"label": "箱を囲む"}]}
        agent_chat.add(db, dataset, "steward", "question", "何をしますか", data=options)
        other = (
            await client.post(
                "/v1/datasets",
                json={"name": "別", "purpose": "p", "image_ids": [ids["a.png"]]},
            )
        ).json()["id"]
        agent_chat.add(db, other, "steward", "failed", "落ちた")
        library = {
            "tool": "dataset_create",
            "args": {"name": "n", "purpose": "p", "paths": [str(tmp_path)]},
            "title": "作る",
            "reason": "r",
        }
        assert (await client.post("/v1/library/proposals", json=library)).is_success
        turns = (await client.get("/v1/turns")).json()
        assert turns["count"] == 4
        assert [p["dataset_id"] for p in turns["places"]] == [None, other, dataset]

        refused = await client.post(
            "/v1/turns/clear",
            json={"dataset_id": dataset},
            headers={"X-Annotation-Agent": "steward"},
        )
        assert refused.status_code == 403
        cleared = await client.post("/v1/turns/clear", json={"dataset_id": dataset})
        assert cleared.json() == {"boxes": 1, "questions": 1, "trouble": 0}
        turns = (await client.get("/v1/turns")).json()
        assert turns["count"] == 2 and dataset not in [
            p["dataset_id"] for p in turns["places"]
        ]
        notes = [
            e["data"]["note"]
            for e in (
                await client.get(f"/v1/datasets/{dataset}/agents/steward/events")
            ).json()["events"]
            if e["kind"] == "note"
        ]
        assert {"box_declined", "question_unanswered"} <= set(notes)

        await client.post("/v1/turns/clear", json={"dataset_id": None})
        assert (await client.get("/v1/turns")).json() == {"count": 0, "places": []}

    scenario(tmp_path, monkeypatch, body)
