"""A label changed in one dataset (definition 79): the library's label stays, the dataset's next
version and its annotations now take the other one, as one record; nothing runs again."""

import asyncio
import json
from uuid import uuid4

from agent_app.image_state import image_states
from agent_app.instructions import latest_basis
from test_runs import DEFINITIONS, finished, run_once, save_version, scenario

from agent_app import runs as runs_module


def _labels(db, dataset_id):
    row = db.one(
        "SELECT payload_json FROM instructions WHERE dataset_id=? ORDER BY revision DESC",
        (dataset_id,),
    )
    return [d["name"] for d in json.loads(row[0])["label_definitions"]]


def _now(db, dataset_id, image_id):
    """The image's annotation now, as the gallery shows it (image_state)."""
    _, states = image_states(db, dataset_id, *latest_basis(db, dataset_id))
    return states[image_id]["now"]["result_id"]


def test_a_label_changed_in_one_dataset_keeps_its_annotations_and_the_others(
    tmp_path, monkeypatch
):
    # User 2026-10-29: a dataset had named a library label wrongly; renaming it changes every
    # dataset using it, and taking it out of the plan meant running every image again.
    from agent_app.sheets import label_objects

    async def body(app, client, dataset, ids):
        db = app.state.db
        other = await client.post(
            "/v1/datasets",
            json={"name": "他", "purpose": "円", "image_ids": [ids["a.png"]]},
        )
        other = other.json()["id"]
        save_version(db, other, {"text": "円を囲む", "label_definitions": DEFINITIONS})
        await run_once(client, app, dataset, image_ids=[ids["a.png"]])
        was = _now(db, dataset, ids["a.png"])
        runs = db.one("SELECT count(*) FROM runs WHERE dataset_id=?", (dataset,))[0]
        circle = next(
            x
            for x in (await client.get("/v1/labels")).json()["items"]
            if x["name"] == "circle"
        )
        box = await client.post(
            f"/v1/datasets/{dataset}/proposals",
            json={
                "agent": "steward",
                "tool": "label_change",
                "args": {"from": "circle", "to": "丸"},
                "title": "circle を 丸 に付け替える",
                "reason": "r",
            },
        )
        assert box.status_code == 201, box.text
        preview = box.json()["preview"]
        assert (preview["from"], preview["to"], preview["images"]) == (
            "circle",
            "丸",
            1,
        )
        applied = await client.post(f"/v1/proposals/{box.json()['id']}/apply", json={})
        assert applied.status_code == 200, applied.text
        assert (_labels(db, dataset), _labels(db, other)) == (["丸"], ["circle"])
        assert (
            db.one("SELECT count(*) FROM runs WHERE dataset_id=?", (dataset,))[0]
            == runs
        )
        made = db.one(
            "SELECT * FROM result_records WHERE id=?",
            (_now(db, dataset, ids["a.png"]),),
        )
        assert made["record_kind"] == "relabel"
        objects = db.execute(
            "SELECT label, geometry_json FROM annotations WHERE set_id=?",
            (made["set_id"],),
        )
        assert [o["label"] for o in objects] == ["丸"]
        assert made["fixed_from"] == was
        assert label_objects(db, circle["id"]) == []
        maru = next(
            x
            for x in (await client.get("/v1/labels")).json()["items"]
            if x["name"] == "丸"
        )
        assert [r["dataset_id"] for r, _ in label_objects(db, maru["id"])] == [dataset]

    scenario(tmp_path, monkeypatch, body)


def test_a_persons_fix_changed_to_another_label_is_still_the_persons(
    tmp_path, monkeypatch
):
    # User 2026-10-30 (the whole flow on the copy): after the change, an image a person fixed
    # said "label changed" and training counted no person's fix.
    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        await run_once(client, app, dataset, image_ids=[a])
        draft = f"/v1/datasets/{dataset}/images/{a}/drafts/fix"
        box = {"label": "circle", "geometry": {"type": "bbox", "xywh": [1, 1, 5, 5]}}
        result = _now(app.state.db, dataset, a)
        await client.put(draft, json={"from_result_id": result, "annotations": [box]})
        assert (await client.post(draft + "/save")).status_code == 201
        changed = await client.post(
            f"/v1/datasets/{dataset}/labels/change", json={"from": "circle", "to": "丸"}
        )
        assert changed.status_code == 200, changed.text
        items = (
            await client.get(f"/v1/datasets/{dataset}/gallery?view=production")
        ).json()["items"]
        badge = next(i["badge"] for i in items if i["image"]["id"] == a)
        assert (badge["by"], badge["record_kind"]) == ("human", "relabel")
        training = (await client.get(f"/v1/datasets/{dataset}/training")).json()
        assert training["parts"]["human"] == 1

    scenario(tmp_path, monkeypatch, body)


def test_a_child_is_not_changed_to_the_child_of_another_parent(tmp_path, monkeypatch):
    # 2026-10-30 review: a child changed to another parent's child was kept under the first
    # parent, a success used for training that the plan's rules refuse.
    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        tree = [
            {"name": n, "shape": "bbox", **({"parent": p} if p else {})}
            for n, p in [("箱A", None), ("箱B", None), ("札A", "箱A"), ("札B", "箱B")]
        ]
        # The run's worker draws the plan's circle; the person's fix the tree.
        plan = [*DEFINITIONS, *tree]
        save_version(app.state.db, dataset, {"text": "囲む", "label_definitions": plan})
        draft = f"/v1/datasets/{dataset}/images/{a}/drafts/fix"
        await run_once(client, app, dataset, image_ids=[a])
        objects = [
            {
                "label": "箱A",
                "ref": "p",
                "geometry": {"type": "bbox", "xywh": [1, 1, 9, 9]},
            },
            {
                "label": "札A",
                "ref": "c",
                "parent": "p",
                "geometry": {"type": "bbox", "xywh": [2, 2, 3, 3]},
            },
        ]
        result = _now(app.state.db, dataset, a)
        await client.put(draft, json={"from_result_id": result, "annotations": objects})
        assert (await client.post(draft + "/save")).status_code == 201
        changed = await client.post(
            f"/v1/datasets/{dataset}/labels/change", json={"from": "札A", "to": "札B"}
        )
        assert changed.json()["error"]["details"] == {"label": "札B", "field": "parent"}
        assert _labels(app.state.db, dataset) == [d["name"] for d in plan]

    scenario(tmp_path, monkeypatch, body)


def test_a_label_change_is_refused_when_it_cannot_carry_the_annotations(
    tmp_path, monkeypatch
):
    async def body(app, client, dataset, ids):
        db = app.state.db
        square = {"name": "square", "shape": "polygon", "attributes": []}
        save_version(
            db,
            dataset,
            {"text": "円を囲む", "label_definitions": [*DEFINITIONS, square]},
        )
        change = f"/v1/datasets/{dataset}/labels/change"
        taken = await client.post(change, json={"from": "circle", "to": "square"})
        assert taken.json()["error"]["code"] == "label_definition_differs"
        release = asyncio.Event()
        real = runs_module.infer

        async def held(*args):
            await release.wait()
            return await real(*args)

        monkeypatch.setattr(runs_module, "infer", held)
        run_id = str(uuid4())
        started = await client.put(
            f"/v1/datasets/{dataset}/runs/{run_id}", json={"image_ids": [ids["a.png"]]}
        )
        assert started.status_code == 201, started.text
        busy = await client.post(change, json={"from": "circle", "to": "丸"})
        assert busy.json()["error"]["code"] == "images_writing"
        release.set()
        await finished(client, run_id)
        assert _labels(db, dataset) == ["circle", "square"]

    scenario(tmp_path, monkeypatch, body)


def test_a_dataset_with_a_label_change_is_written_out_and_taken_in_again(
    tmp_path, monkeypatch
):
    # Definition 79.4: a record of a new kind travels with the dataset's other records.
    async def body(app, client, dataset, ids):
        db = app.state.db
        await run_once(client, app, dataset, image_ids=[ids["a.png"]])
        changed = await client.post(
            f"/v1/datasets/{dataset}/labels/change", json={"from": "circle", "to": "丸"}
        )
        assert changed.status_code == 200, changed.text
        out = tmp_path / "out"
        out.mkdir()
        asked = {"dataset_ids": [dataset], "dest": str(out), "format": "app"}
        await client.post("/v1/library/export", json=asked)
        taken = await client.post("/v1/library/import", json={"path": str(out)})
        assert taken.status_code == 200, taken.text
        (made,) = taken.json()["datasets"]
        result = db.one(
            "SELECT * FROM result_records WHERE id=?",
            (_now(db, made["id"], ids["a.png"]),),
        )
        assert result["record_kind"] == "relabel" and result["fixed_from"] is not None
        # And deleted with its records (definition 79.4).
        deleted = await client.delete(f"/v1/datasets/{dataset}")
        assert deleted.status_code == 200, deleted.text
        assert (
            db.one("SELECT count(*) FROM copies WHERE dataset_id=?", (dataset,))[0] == 0
        )

    scenario(tmp_path, monkeypatch, body)
