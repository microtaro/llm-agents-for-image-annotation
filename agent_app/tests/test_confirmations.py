"""A person checks annotations by a version's criteria (definition 85.5)."""

from agent_app.image_state import image_states, state_counts
from agent_app.instructions import latest_basis, latest_revision
from test_runs import DEFINITIONS, run_once, save_version, scenario


def test_a_person_checks_annotations_by_the_criteria_now(tmp_path, monkeypatch):
    # 2026-10-30: after the criteria changed, the earlier annotations are not done by them
    # until run again or checked; checking one that has none changes nothing.
    async def body(app, client, dataset, ids):
        db = app.state.db
        a, failed = ids["a.png"], ids["fail.png"]
        await run_once(client, app, dataset)
        plan = {
            "text": "円を囲む。",
            "label_definitions": DEFINITIONS,
            "leave_out": ["欠けた円"],
        }
        save_version(db, dataset, plan)
        revision = latest_revision(db, dataset)
        path = f"/v1/datasets/{dataset}/confirmations"
        refused = await client.post(
            path, json={"image_ids": [a, failed], "revision": revision}
        )
        assert refused.json()["error"]["code"] == "nothing_to_confirm"
        assert db.one("SELECT count(*) FROM confirmations")[0] == 0
        checked = await client.post(path, json={"image_ids": [a], "revision": revision})
        assert checked.status_code == 200, checked.text
        _, states = image_states(db, dataset, *latest_basis(db, dataset))
        assert states[a]["now"]["checked"] is True
        assert (state_counts(states)["done"], state_counts(states)["other"]) == (1, 0)

    scenario(tmp_path, monkeypatch, body)


def test_a_new_text_keeps_the_annotations_done(tmp_path, monkeypatch):
    # 2026-10-30 (user: "この確かめ、普段からしょっちゅうでるようだと、使いにくい"): the plan's
    # text or a label's description said again made every annotation another criteria's; only
    # what is not annotated does (definition 85.16).
    async def body(app, client, dataset, ids):
        db = app.state.db
        a = ids["a.png"]
        await run_once(client, app, dataset, image_ids=[a])
        circle = {**DEFINITIONS[0], "description": "丸い物"}
        save_version(
            db, dataset, {"text": "円を外側の枠で囲む", "label_definitions": [circle]}
        )
        _, states = image_states(db, dataset, *latest_basis(db, dataset))
        assert states[a]["now"]["criteria"] == "this"
        assert state_counts(states)["done"] == 1
        save_version(
            db,
            dataset,
            {
                "text": "円を外側の枠で囲む",
                "label_definitions": [circle],
                "leave_out": ["欠けた円"],
            },
        )
        _, states = image_states(db, dataset, *latest_basis(db, dataset))
        assert states[a]["now"]["criteria"] == "other"

    scenario(tmp_path, monkeypatch, body)
