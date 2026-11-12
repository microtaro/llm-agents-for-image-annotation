"""The work room's proposals (step 22, trial C): a decision made ready, applied by a person
through the same tool and API, or declined; kept with what came of it."""

from test_runs import scenario


def test_a_proposal_is_applied_through_its_tool_or_declined(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        base = f"/v1/datasets/{dataset}/proposals"
        mark = {
            "bot": "production",
            "tool": "mark",
            "args": {
                "dataset_id": dataset,
                "target": "image",
                "image_id": ids["a.png"],
                "excluded": True,
            },
            "title": "a を学習に使わない",
            "reason": "写りが悪い",
        }

        async def excluded():
            items = (await client.get(f"/v1/datasets/{dataset}/adoption")).json()[
                "items"
            ]
            return [i["image_id"] for i in items if i["source"] == "excluded"]

        made = await client.post(base, json=mark, headers={"X-Actor": "ai"})
        assert made.status_code == 201, made.text
        assert (made.json()["state"], made.json()["made_by"]) == ("open", "outside")
        # User 2026-10-09: a decided box looked like one to decide; the server says which.
        assert (made.json()["waiting"], made.json()["decided"]) == (True, False)
        # Nothing changed until a person applies it.
        assert await excluded() == []
        applied = await client.post(
            f"/v1/proposals/{made.json()['id']}/apply", headers={"X-Actor": "ui"}
        )
        assert applied.status_code == 200, applied.text
        assert (applied.json()["state"], applied.json()["decided_by"]) == (
            "applied",
            "person",
        )
        assert await excluded() == [ids["a.png"]]
        again = await client.post(f"/v1/proposals/{made.json()['id']}/apply")
        assert again.status_code == 409
        other = await client.post(base, json=mark)
        declined = await client.post(f"/v1/proposals/{other.json()['id']}/decline")
        assert declined.json()["state"] == "declined"
        assert (declined.json()["waiting"], declined.json()["decided"]) == (
            False,
            False,
        )
        listed = (await client.get(base)).json()["proposals"]
        assert [p["state"] for p in listed] == ["declined", "applied"]
        # Arguments of another dataset are refused when made, not when applied.
        wrong = await client.post(
            base, json={**mark, "args": {**mark["args"], "dataset_id": "elsewhere"}}
        )
        assert wrong.status_code == 422
        # A dataset with proposals can be deleted.
        deleted = await client.delete(f"/v1/datasets/{dataset}")
        assert deleted.status_code in (200, 204), deleted.text

    scenario(tmp_path, monkeypatch, body)


def test_a_proposals_work_area_comes_from_its_tool_not_from_what_was_said(
    tmp_path, monkeypatch
):
    # Step 23 (the box): the work area opened with a decision is the map's, by rule.
    async def body(app, client, dataset, ids):
        base = f"/v1/datasets/{dataset}/proposals"
        said = {"title": "t", "reason": "r", "bot": "instruction"}
        trial = await client.post(
            base,
            json={
                **said,
                "bot": "production",
                "tool": "run_start",
                "args": {
                    "dataset_id": dataset,
                    "budget_per_image_usd": "1",
                    "image_ids": [ids["a.png"]],
                    "trial": True,
                },
            },
        )
        run = await client.post(
            base,
            json={
                **said,
                "tool": "run_start",
                "args": {
                    "dataset_id": dataset,
                    "budget_per_image_usd": "1",
                    "image_ids": [ids["a.png"]],
                },
            },
        )
        assert trial.status_code == 201, trial.text
        assert (trial.json()["bot"], run.json()["bot"]) == ("instruction", "production")
        one = await client.get(f"/v1/proposals/{run.json()['id']}")
        assert one.json()["args"]["image_ids"] == [ids["a.png"]]

    scenario(tmp_path, monkeypatch, body)


def test_a_persons_own_decision_is_done_at_once_and_never_waits(tmp_path, monkeypatch):
    """User 2026-10-13: a person's press was put in the line as a box, to be decided again, and
    an older box came up in its place. A person's own decision is checked once (preview) and
    done; only a worker's proposal waits."""

    async def body(app, client, dataset, ids):
        decision = {
            "tool": "mark",
            "args": {"target": "image", "image_id": ids["a.png"], "excluded": True},
            "title": "a を学習に使わない",
            "reason": "画面のボタンから",
        }
        seen = await client.post(
            f"/v1/datasets/{dataset}/proposals/preview", json=decision
        )
        assert seen.status_code == 200, seen.text
        assert seen.json()["preview"]["excluded_now"] is False
        assert (await client.get(f"/v1/datasets/{dataset}/proposals")).json()[
            "proposals"
        ] == []
        done = await client.post(
            f"/v1/datasets/{dataset}/decisions",
            json=decision,
            headers={"X-Actor": "ui"},
        )
        assert done.status_code == 201, done.text
        # A decision, not a box (definition 21.3): nothing waits or is listed as a proposal.
        assert (done.json()["kind"], done.json()["decided_by"]) == ("use", "person")
        listed = (await client.get(f"/v1/datasets/{dataset}/proposals")).json()
        assert listed["proposals"] == []
        # A worker cannot decide this way.
        refused = await client.post(
            f"/v1/datasets/{dataset}/decisions",
            json=decision,
            headers={"x-annotation-agent": "steward"},
        )
        assert refused.status_code == 403

    scenario(tmp_path, monkeypatch, body)


def test_a_box_left_being_applied_is_settled_when_the_server_starts(
    tmp_path, monkeypatch
):
    # Review 2026-10-28 (B#18): the server stopped while a box was applied left it "applying"
    # for ever, never to be decided. Its tool records the decision with what it changed, in one
    # transaction: with the decision it was applied, without it nothing changed.
    from agent_app.app import create_app

    async def body(app, client, dataset, ids):
        base = f"/v1/datasets/{dataset}/proposals"

        def mark(image):
            return {
                "title": "t",
                "reason": "r",
                "tool": "mark",
                "args": {"target": "image", "image_id": ids[image], "excluded": True},
            }

        boxes = [
            (await client.post(base, json=mark(image))).json()["id"]
            for image in ("a.png", "fail.png")
        ]
        db = app.state.db
        db.execute(
            "UPDATE proposals SET state='applying' WHERE dataset_id=?", (dataset,)
        )
        db.execute(
            "INSERT INTO decisions(id, dataset_id, kind, content_json, decided_by,"
            " requested_by, proposal_id, outcome_json, decided_at)"
            " VALUES('dec-done', ?, 'use', '{}', 'ui', 'agent:steward', ?, '{}', 'x')",
            (dataset, boxes[0]),
        )
        again = create_app(tmp_path / "runs.db")
        async with again.router.lifespan_context(again):
            states = [
                again.state.db.one("SELECT state FROM proposals WHERE id=?", (b,))[0]
                for b in boxes
            ]
        assert states == ["applied", "open"]

    scenario(tmp_path, monkeypatch, body)
