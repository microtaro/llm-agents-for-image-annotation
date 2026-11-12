"""A label's own id (definition 23; issue #4 F-01: renaming a label made every earlier result
one of another requirement, left out of training)."""

import json

from agent_app.decisions import get_decision
from agent_app.image_state import image_states
from agent_app.instructions import latest_basis, latest_row, requirement_key
from test_runs import DEFINITIONS, run_once, save_version, scenario

PERSON = {"X-Actor": "ui"}


def _latest(db, dataset):
    return latest_row(db, dataset)


def test_a_renamed_label_is_the_same_label(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        db = app.state.db
        await run_once(client, app, dataset)
        before = _latest(db, dataset)
        renamed = await client.post(
            f"/v1/datasets/{dataset}/labels/rename",
            json={"from": "circle", "to": "丸"},
            headers=PERSON,
        )
        assert renamed.status_code == 200, renamed.text
        after = _latest(db, dataset)
        assert after["requirement_key"] == before["requirement_key"]
        # The earlier success is still of the plan now: used, named as now.
        assert (
            image_states(db, dataset, *latest_basis(db, dataset))[1][ids["a.png"]][
                "used"
            ]
            == "result"
        )
        items = (
            await client.get(f"/v1/datasets/{dataset}/gallery?view=production")
        ).json()["items"]
        shown = next(i for i in items if i["image"]["id"] == ids["a.png"])
        assert {a["label"] for a in shown["annotations"]} == {"丸"}
        exported = (
            await client.get(f"/v1/datasets/{dataset}/adoption/annotations")
        ).json()["items"]
        assert {a["label"] for i in exported for a in i["annotations"]} == {"丸"}
        # Only the description changed: the same; another shape: another requirement.
        definitions = json.loads(after["payload_json"])["label_definitions"]
        described = [{**definitions[0], "description": "丸い物"}]
        assert requirement_key(described) == after["requirement_key"]
        reshaped = [{**definitions[0], "shape": "polygon"}]
        assert requirement_key(reshaped) != after["requirement_key"]

    scenario(tmp_path, monkeypatch, body)


def test_a_rename_outlives_the_dataset_it_was_asked_in(tmp_path, monkeypatch):
    # 2026-10-30 review: the rename was kept as the first dataset's decision; deleting that
    # dataset took the decision the other dataset's version was made by.
    async def body(app, client, dataset, ids):
        db = app.state.db
        other = await client.post(
            "/v1/datasets",
            json={"name": "他", "purpose": "円", "image_ids": [ids["a.png"]]},
        )
        other = other.json()["id"]
        save_version(db, other, {"text": "円を囲む", "label_definitions": DEFINITIONS})
        renamed = await client.post(
            f"/v1/datasets/{dataset}/labels/rename",
            json={"from": "circle", "to": "丸"},
            headers=PERSON,
        )
        assert renamed.status_code == 200, renamed.text
        deleted = await client.delete(f"/v1/datasets/{dataset}", headers=PERSON)
        assert deleted.status_code == 200, deleted.text
        made_by = _latest(db, other)["decision_id"]
        assert get_decision(db, made_by)["content"]["to"] == "丸"

    scenario(tmp_path, monkeypatch, body)


def test_a_version_made_by_a_rename_says_the_label_was_renamed(tmp_path, monkeypatch):
    # 2026-10-30 (the whole flow on the copy): its "from the version before" said one label
    # added and one removed.
    async def body(app, client, dataset, ids):
        renamed = await client.post(
            f"/v1/datasets/{dataset}/labels/rename",
            json={"from": "circle", "to": "丸"},
            headers=PERSON,
        )
        assert renamed.status_code == 200, renamed.text
        revision = _latest(app.state.db, dataset)["revision"]
        diff = (
            await client.get(f"/v1/datasets/{dataset}/instructions/{revision}/diff")
        ).json()
        said = (
            await client.get(f"/v1/datasets/{dataset}/objects/version/{revision}")
        ).json()["from_previous"]
        for found in (diff, said):
            assert (found["added"], found["removed"], found["renamed"]) == (
                [],
                [],
                [["circle", "丸"]],
            )

    scenario(tmp_path, monkeypatch, body)


def test_versions_taken_in_keep_their_names_and_where_they_started(
    tmp_path, monkeypatch
):
    # 2026-10-30 (the whole flow on the copy): written out and taken in, the version before a
    # rename took the name now, and no version said where it was started from.
    async def body(app, client, dataset, ids):
        renamed = await client.post(
            f"/v1/datasets/{dataset}/labels/rename",
            json={"from": "circle", "to": "丸"},
            headers=PERSON,
        )
        assert renamed.status_code == 200, renamed.text
        out = tmp_path / "out"
        out.mkdir()
        asked = {"dataset_ids": [dataset], "dest": str(out), "format": "app"}
        await client.post("/v1/library/export", json=asked)
        taken = await client.post("/v1/library/import", json={"path": str(out)})
        assert taken.status_code == 200, taken.text
        (made,) = taken.json()["datasets"]

        async def version(d, revision):
            got = await client.get(f"/v1/datasets/{d}/instructions/{revision}")
            return got.json()

        for revision in (1, 2):
            was, now = (
                await version(dataset, revision),
                await version(made["id"], revision),
            )
            assert [d["name"] for d in now["label_definitions"]] == [
                d["name"] for d in was["label_definitions"]
            ]
        assert (await version(made["id"], 2))["from"] == {
            "kind": "version",
            "dataset_id": made["id"],
            "revision": 1,
        }

    scenario(tmp_path, monkeypatch, body)


def test_a_rename_reaches_a_plan_that_is_only_a_draft(tmp_path, monkeypatch):
    # Test C12 (10-28): a dataset whose plan was copied from another had the label in its
    # draft only; renaming the label left it there under the old name.
    async def body(app, client, dataset, ids):
        other = (
            await client.post(
                "/v1/datasets",
                json={"name": "写し", "purpose": "円", "image_ids": [ids["a.png"]]},
            )
        ).json()["id"]
        started = await client.post(
            f"/v1/datasets/{other}/plan/start",
            json={"kind": "other", "dataset_id": dataset, "revision": 1},
        )
        assert started.status_code == 200, started.text
        renamed = await client.post(
            f"/v1/datasets/{dataset}/labels/rename",
            json={"from": "circle", "to": "丸"},
            headers=PERSON,
        )
        assert renamed.status_code == 200, renamed.text
        draft = (await client.get(f"/v1/datasets/{other}/drafts/instruction")).json()
        assert [d["name"] for d in draft["label_definitions"]] == ["丸"]
        # And from the dataset with the draft only, back again.
        back = await client.post(
            f"/v1/datasets/{other}/labels/rename",
            json={"from": "丸", "to": "circle"},
            headers=PERSON,
        )
        assert back.status_code == 200, back.text
        assert _latest(app.state.db, other) is None

    scenario(tmp_path, monkeypatch, body)


def test_a_rename_reaches_a_fix_being_made(tmp_path, monkeypatch):
    # 2026-10-30 (fact inventory 6): a rename wrote a fix being made back as it was, so its
    # objects kept the old name and saving it was refused.
    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        await run_once(client, app, dataset)
        items = (await client.get(f"/v1/datasets/{dataset}/adoption")).json()["items"]
        result = next(i for i in items if i["image_id"] == a)["result_id"]
        draft = f"/v1/datasets/{dataset}/images/{a}/drafts/fix"
        box = {"label": "circle", "geometry": {"type": "bbox", "xywh": [1, 1, 5, 5]}}
        await client.put(draft, json={"from_result_id": result, "annotations": [box]})
        renamed = await client.post(
            f"/v1/datasets/{dataset}/labels/rename",
            json={"from": "circle", "to": "丸"},
            headers=PERSON,
        )
        assert renamed.status_code == 200, renamed.text
        held = (await client.get(draft)).json()
        assert [x["label"] for x in held["annotations"]] == ["丸"]
        saved = await client.post(draft + "/save")
        assert saved.status_code == 201, saved.text

    scenario(tmp_path, monkeypatch, body)


def test_a_reference_is_drawn_in_its_label_color_after_a_rename(tmp_path, monkeypatch):
    # 2026-11-10: a reference chosen before its label was renamed was drawn in the old name's
    # color, not in the one its worker is told for the new name (label_colors).
    async def body(app, client, dataset, ids):
        first = await run_once(client, app, dataset, image_ids=[ids["a.png"]])
        result_id = (await client.get(f"/v1/runs/{first['id']}/results")).json()[
            "results"
        ][0]["result_id"]
        chosen = await client.put(
            f"/v1/datasets/{dataset}/images/{ids['a.png']}/reference",
            json={"result_id": result_id, "note": ""},
        )
        assert chosen.status_code == 200, chosen.text
        renamed = await client.post(
            f"/v1/datasets/{dataset}/labels/rename",
            json={"from": "circle", "to": "丸"},
            headers=PERSON,
        )
        assert renamed.status_code == 200, renamed.text
        second = await run_once(client, app, dataset, image_ids=[ids["fail.png"]])
        told = json.loads(
            app.state.db.one(
                "SELECT settings_json FROM runs WHERE id=?", (second["id"],)
            )[0]
        )["label_colors"]
        ((_, ref, frame),) = app.state.seen_refs
        assert {a["label"] for a in ref["annotations"]} == {"丸"}
        assert told["丸"] != told.get("circle")
        assert set(frame["label_colors"].values()) == {told["丸"]}

    scenario(tmp_path, monkeypatch, body)
