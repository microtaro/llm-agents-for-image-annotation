"""Results carried over from another version or dataset (definition 85.15)."""

from agent_app.annotation_sets import current
from agent_app.image_state import image_states
from agent_app.instructions import latest_basis, latest_revision
from agent_app.run_queries import result_row
from test_runs import DEFINITIONS, run_once, save_version, scenario


def _now(db, dataset, image_id):
    return image_states(db, dataset, *latest_basis(db, dataset))[1][image_id]["now"]


def test_boxes_come_over_when_a_label_is_added(tmp_path, monkeypatch):
    # 2026-10-30 (user: "属性の変更について"): a plan whose labels changed made every result
    # one of an earlier requirement, the boxes all to draw again. (An attribute added no longer
    # changes the requirement, definition 85.17: a label added does.)
    async def body(app, client, dataset, ids):
        db = app.state.db
        a = ids["a.png"]
        await run_once(client, app, dataset, image_ids=[a])
        square = {"name": "square", "shape": "bbox", "attributes": []}
        save_version(
            db,
            dataset,
            {"text": "円と四角を囲む", "label_definitions": [*DEFINITIONS, square]},
        )
        assert _now(db, dataset, a) is None
        carried = await client.post(
            f"/v1/datasets/{dataset}/carry",
            json={"from_dataset_id": dataset, "from_revision": 1},
        )
        assert carried.status_code == 200, carried.text
        assert carried.json()["skipped"]["none"] == 1  # fail.png had nothing
        now = _now(db, dataset, a)
        objects = current(db, result_row(db, now["result_id"])["set_id"])
        assert [o["attributes"] for o in objects] == [{"color": "red"}]
        # Made by the AI, by the criteria of version 1 (the same: nothing more is left out),
        # used for training.
        assert (now["by"], now["criteria"], now["record_kind"]) == (
            "ai",
            "this",
            "carry",
        )
        states = image_states(db, dataset, *latest_basis(db, dataset))[1]
        assert states[a]["used"] == "result"
        # Nothing to carry any more: refused, nothing written.
        again = await client.post(
            f"/v1/datasets/{dataset}/carry",
            json={"from_dataset_id": dataset, "from_revision": 1},
        )
        assert again.json()["error"]["code"] == "nothing_to_carry"

    scenario(tmp_path, monkeypatch, body)


def test_results_come_from_another_dataset_with_the_images(tmp_path, monkeypatch):
    # 2026-10-30 (user: searching to make data felt cramped): results made in another dataset
    # come to the images this one has, by the library's labels.
    async def body(app, client, dataset, ids):
        db = app.state.db
        a = ids["a.png"]
        other = await client.post(
            "/v1/datasets",
            json={"name": "他", "purpose": "円", "image_ids": [a]},
        )
        other = other.json()["id"]
        # Made there by other criteria (more left out than here, definition 85.16).
        save_version(
            db,
            other,
            {
                "text": "円を囲む",
                "label_definitions": DEFINITIONS,
                "leave_out": ["欠けた円"],
            },
        )
        await run_once(client, app, other, image_ids=[a])
        # This dataset's plan: the same label and another one.
        square = {"name": "square", "shape": "bbox", "attributes": []}
        save_version(
            db,
            dataset,
            {"text": "円と四角を囲む", "label_definitions": [*DEFINITIONS, square]},
        )
        carried = await client.post(
            f"/v1/datasets/{dataset}/carry",
            json={
                "from_dataset_id": other,
                "from_revision": latest_revision(db, other),
            },
        )
        assert carried.status_code == 200, carried.text
        # fail.png is not an image of the other dataset.
        assert carried.json()["skipped"]["not_there"] == 1
        now = _now(db, dataset, a)
        assert now["record_kind"] == "carry" and now["criteria"] == "other"
        objects = current(db, result_row(db, now["result_id"])["set_id"])
        assert [o["label"] for o in objects] == ["circle"]
        # Deleting the dataset it came from leaves it as it was copied.
        assert (await client.delete(f"/v1/datasets/{other}")).status_code == 200
        kept = _now(db, dataset, a)
        assert (kept["result_id"], kept["by"], kept["criteria"]) == (
            now["result_id"],
            "ai",
            "other",
        )

    scenario(tmp_path, monkeypatch, body)


def test_each_image_carried_keeps_its_own_criteria(tmp_path, monkeypatch):
    # 2026-10-30 (acceptance of 85.17 on the copy): one carry record held results made by two
    # criteria, and the first image's was said of every image of the record.
    async def body(app, client, dataset, ids):
        db = app.state.db
        a, b = ids["a.png"], ids["fail.png"]
        await run_once(client, app, dataset)
        left_out = {"text": "円を囲む", "leave_out": ["欠けた円"]}
        save_version(db, dataset, {**left_out, "label_definitions": DEFINITIONS})
        await run_once(client, app, dataset, image_ids=[a])
        square = {"name": "square", "shape": "bbox", "attributes": []}
        save_version(
            db, dataset, {**left_out, "label_definitions": [*DEFINITIONS, square]}
        )
        carried = await client.post(
            f"/v1/datasets/{dataset}/carry",
            json={"from_dataset_id": dataset, "from_revision": 2},
        )
        assert carried.status_code == 200, carried.text
        # a.png's was made by version 2 (the same left out), b's by version 1 (none).
        assert (_now(db, dataset, a)["criteria"], _now(db, dataset, b)["criteria"]) == (
            "this",
            "other",
        )

    scenario(tmp_path, monkeypatch, body, fail_names=())
