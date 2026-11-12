"""The plan's state by its items (definition 26.3) that the map, the screen and the workers
share, what the draft changed, and rules for a draft's labels."""

from test_runs import DEFINITIONS, run_once, scenario

WORKER = {"X-Annotation-Agent": "steward"}
PERSON = {"X-Actor": "ui"}


def test_who_decided_each_item_of_the_plan(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        base = f"/v1/datasets/{dataset}"

        async def state():
            found = (await client.get(f"{base}/plan/state")).json()
            return {i["item"]: i["status"] for i in found["items"]}, found["next"]

        # Saved from the outside and never run: the labels are decided, the rest is open.
        items, following = await state()
        assert (items["requirement"], items["references"], items["trial"]) == (
            "person",
            "open",
            "open",
        )
        assert following == "leave_out"
        plan = {"text": "円を囲む", "label_definitions": DEFINITIONS}
        await client.put(
            f"{base}/drafts/instruction",
            json={**plan, "leave_out": ["欠けた円"]},
            headers=WORKER,
        )
        items, following = await state()
        assert (items["leave_out"], items["requirement"], following) == (
            "agent",
            "person",
            "references",
        )
        await client.put(
            f"{base}/drafts/instruction",
            json={**plan, "leave_out": ["欠けた円", "影"]},
            headers=PERSON,
        )
        items, _ = await state()
        assert items["leave_out"] == "person"
        # Run as it is (a trial): a person decided every item of it.
        await run_once(client, app, dataset, trial=True, image_ids=[a])
        items, following = await state()
        assert set(items.values()) == {"person"} and following is None
        progress = (await client.get(f"{base}/progress")).json()
        assert progress["stages"][0]["state"] == "done"

    scenario(tmp_path, monkeypatch, body)


def test_what_the_draft_changed_since_the_version(tmp_path, monkeypatch):
    # Step 19 design 4: shown above ①'s cards, so the draft is seen without opening the panel.
    async def body(app, client, dataset, ids):
        base = f"/v1/datasets/{dataset}"
        latest = (await client.get(f"{base}/instructions/latest")).json()
        await client.put(
            f"{base}/drafts/instruction",
            json={
                "text": latest["text"] + "\n縁が欠けた円も囲む。",
                "label_definitions": [
                    {**d, "description": d.get("description", "") + " 欠けも含む"}
                    for d in latest["label_definitions"]
                ],
            },
        )
        diff = (await client.get(f"{base}/drafts/instruction/diff")).json()
        assert diff["text"]["added"] == ["縁が欠けた円も囲む。"]
        assert diff["text"]["removed"] == []
        assert diff["described"] == ["circle"] and diff["changed"] == []
        await client.delete(f"{base}/drafts/instruction")
        gone = await client.get(f"{base}/drafts/instruction/diff")
        assert gone.status_code == 404

    scenario(tmp_path, monkeypatch, body)


def test_two_contents_are_compared(tmp_path, monkeypatch):
    # Step 19: one answer's change (a draft against the draft before it), not all since the
    # version; the same words as against the version.
    async def body(app, client, dataset, ids):
        old = {"text": "円を囲む。", "label_definitions": DEFINITIONS, "references": []}
        new = {
            **old,
            "text": "円を囲む。欠けた円も囲む。",
            "label_definitions": [{**d, "description": "丸い物"} for d in DEFINITIONS],
        }
        diff = (
            await client.post(
                f"/v1/datasets/{dataset}/drafts/instruction/compare",
                json={"old": old, "new": new},
            )
        ).json()
        assert diff["text"]["added"] == ["欠けた円も囲む。"]
        assert diff["described"] == [d["name"] for d in DEFINITIONS]
        first = (
            await client.post(
                f"/v1/datasets/{dataset}/drafts/instruction/compare",
                json={"old": None, "new": new},
            )
        ).json()
        assert first["added"] == [d["name"] for d in DEFINITIONS]

    scenario(tmp_path, monkeypatch, body)
