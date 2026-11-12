"""Attributes are not the requirement (definition 85.17): a value missing is counted where the
attribute is used, the boxes stay the annotation now."""

from agent_app.annotation_sets import current
from agent_app.image_state import image_states
from agent_app.instructions import latest_basis
from agent_app.run_queries import result_row
from test_runs import DEFINITIONS, run_once, save_version, scenario

SIZE = {"name": "size", "type": "choice", "choices": ["small", "large"]}


def _now(db, dataset, image_id):
    return image_states(db, dataset, *latest_basis(db, dataset))[1][image_id]["now"]


def test_an_attribute_added_keeps_the_boxes_and_counts_it_not_filled(
    tmp_path, monkeypatch
):
    # 2026-10-30 (an outside review the user pasted): an attribute added made every box an
    # earlier requirement's result, to be copied back each time; the boxes are there, the
    # value is not filled.
    async def body(app, client, dataset, ids):
        db = app.state.db
        a = ids["a.png"]
        await run_once(client, app, dataset, image_ids=[a])
        circle = {**DEFINITIONS[0], "attributes": [*DEFINITIONS[0]["attributes"], SIZE]}
        save_version(db, dataset, {"text": "円を囲む", "label_definitions": [circle]})
        assert _now(db, dataset, a)["criteria"] == "this"
        shown = (
            await client.get(
                f"/v1/datasets/{dataset}/gallery", params={"view": "production"}
            )
        ).json()
        badge = next(i["badge"] for i in shown["items"] if i["image"]["id"] == a)
        assert badge["unfilled"] == ["size"]
        assert (shown["counts"]["done"], shown["unfilled"]) == (1, {"size": 1})
        # Nothing to copy back: the image has its annotation.
        carried = await client.post(
            f"/v1/datasets/{dataset}/carry",
            json={"from_dataset_id": dataset, "from_revision": 1},
        )
        assert carried.json()["error"]["code"] == "nothing_to_carry"

    scenario(tmp_path, monkeypatch, body)


def test_a_fix_of_an_earlier_version_keeps_only_the_plans_values(tmp_path, monkeypatch):
    # 2026-10-30: with an attribute taken off, a fix starting from the result made before
    # carries its value, which the plan no longer has.
    async def body(app, client, dataset, ids):
        db = app.state.db
        a = ids["a.png"]
        await run_once(client, app, dataset, image_ids=[a])
        plain = {**DEFINITIONS[0], "attributes": []}
        save_version(db, dataset, {"text": "円を囲む", "label_definitions": [plain]})
        fixed = await client.post(
            f"/v1/datasets/{dataset}/images/{a}/fixes",
            json={
                "from_result_id": _now(db, dataset, a)["result_id"],
                "annotations": [
                    {
                        "label": "circle",
                        "geometry": {"type": "bbox", "xywh": [1, 1, 5, 5]},
                        "attributes": {"color": "red"},
                    }
                ],
            },
        )
        assert fixed.status_code == 201, fixed.text
        objects = current(db, result_row(db, fixed.json()["result_id"])["set_id"])
        assert [o["attributes"] for o in objects] == [{}]

    scenario(tmp_path, monkeypatch, body)
