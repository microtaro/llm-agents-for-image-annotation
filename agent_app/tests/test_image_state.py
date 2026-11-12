"""The state of each image, from one place (definition 14)."""

from agent_app.adoption import adoption
from agent_app.gallery import gallery
from agent_app.image_state import image_states
from agent_app.instructions import latest_basis, latest_payload
from agent_app.object_types import query
from PIL import Image
from test_runs import DEFINITIONS, fake_inference, run_once, save_version, scenario

from agent_app import runs as runs_module


async def previewed(client, dataset, args):
    """What a run's decision shows, as the screen asks for it (its values by the decision's
    rules first, as every box's are)."""
    found = await client.post(
        f"/v1/datasets/{dataset}/proposals/preview",
        json={"tool": "run_start", "args": args, "title": "t", "reason": "r"},
    )
    assert found.status_code == 200, found.text
    return found.json()["preview"]


# Another requirement (the worker of the tests still finds circles).
WITH_SQUARES = [*DEFINITIONS, {"name": "square", "shape": "bbox", "attributes": []}]


def test_an_image_says_the_same_in_every_view(tmp_path, monkeypatch):
    # Astra 2026-10-17 (P01, P02, P07): a card had a result and the loupe "objects (0)", a box
    # said "failed · used for training", the table "no result" for a left out image with one.
    async def body(app, client, _dataset, _ids):
        db = app.state.db
        ids = {}
        for index, name in enumerate("abcdef"):
            path = tmp_path / f"{name}.png"
            Image.new("RGB", (240, 120), (index * 30, 90, 10)).save(path)
            imported = await client.post(
                "/v1/images/import", json={"paths": [str(path)]}
            )
            ids[name] = imported.json()["images"][0]["id"]
        dataset = (
            await client.post(
                "/v1/datasets",
                json={"name": "六枚", "purpose": "p", "image_ids": list(ids.values())},
            )
        ).json()["id"]
        save_version(
            app.state.db, dataset, {"text": "円", "label_definitions": DEFINITIONS}
        )

        async def run(names, fail=()):
            failing = tuple(f"{n}.png" for n in fail)
            monkeypatch.setattr(
                runs_module, "infer", fake_inference(app, fail_names=failing)
            )
            return await run_once(
                client, app, dataset, image_ids=[ids[n] for n in names]
            )

        def result_of(run_id, name):
            return db.one(
                "SELECT id FROM results WHERE run_id=? AND image_id=?",
                (run_id, ids[name]),
            )["id"]

        # d: only a result of the requirement before.
        await run(["d"])
        save_version(
            app.state.db, dataset, {"text": "四角", "label_definitions": WITH_SQUARES}
        )
        # a: a success, then a failure. b: two successes, the older one chosen by a person.
        # c: a success, then left out. e: failures only.
        first = await run(["a", "b", "c", "e"], fail=["e"])
        second = await run(["a", "b"], fail=["a"])
        picked = await client.put(
            f"/v1/datasets/{dataset}/images/{ids['b']}/adoption",
            json={"result_id": result_of(first["id"], "b")},
        )
        assert picked.status_code == 200, picked.text
        await client.post(f"/v1/datasets/{dataset}/images/{ids['c']}/exclude")
        # f: being made.
        with db.transaction():
            db.execute(
                "INSERT INTO runs(id,dataset_id,status,instruction_revision,requirement_key,"
                "requested_json,worker_prompt,worker_prompt_sha256,settings_json,request_json,"
                "budget_per_image_usd,started_at,number) SELECT 'going',dataset_id,'running',revision,"
                "requirement_key,'[]','p','s','{\"model\": \"gpt-6-luna\"}','{}','1',"
                "'2026-10-17T00:00:00Z',99 FROM instructions WHERE dataset_id=? AND revision=2",
                (dataset,),
            )
            db.execute(
                "INSERT INTO annotation_sets(id, image_id) VALUES('going-set', ?)",
                (ids["f"],),
            )
            db.execute(
                "INSERT INTO results(id,run_id,image_id,set_id,position,status)"
                " VALUES('going-f','going',?,'going-set',0,'pending')",
                (ids["f"],),
            )

        _, states = image_states(db, dataset, *latest_basis(db, dataset))
        by_name = {n: states[i] for n, i in ids.items()}
        now = {n: (s["now"] or {}).get("result_id") for n, s in by_name.items()}
        used = {n: s["used"] for n, s in by_name.items()}
        assert now == {
            "a": result_of(first["id"], "a"),
            "b": result_of(first["id"], "b"),
            "c": result_of(first["id"], "c"),
            "d": None,
            "e": None,
            "f": None,
        }
        assert used == {
            "a": "result",
            "b": "result",
            "c": "excluded",
            "d": "stale",
            "e": "none",
            "f": "none",
        }
        assert by_name["b"]["now"]["picked"] and by_name["b"]["now"]["newer"]
        assert by_name["a"]["latest"]["result_id"] == result_of(second["id"], "a")
        assert by_name["a"]["failures"]["parts"] == [{"revision": 2, "count": 1}]
        assert by_name["e"]["failures"]["parts"] == [{"revision": 2, "count": 1}]
        assert by_name["f"]["running"] and not by_name["e"]["running"]

        names = {i: n for n, i in ids.items()}

        def per_image(items, read, key=lambda i: i["image"]["id"]):
            return {names[key(i)]: read(i) for i in items}

        # The adoption, the gallery's three views, a box's preview and the type list agree.
        sources = per_image(
            adoption(db, dataset)["items"],
            lambda i: i["source"],
            lambda i: i["image_id"],
        )
        assert sources == used
        for view in ("adoption", "production"):
            found = per_image(
                gallery(db, dataset, view, latest_payload(db, dataset))["items"],
                lambda i: i["badge"],
            )
            assert {n: found[n].get("result_id") for n in "abc"} == {
                n: now[n] for n in "abc"
            }
            assert found["c"]["kind"] == "excluded"
        shown = per_image(
            gallery(db, dataset, "run", latest_payload(db, dataset))["items"],
            lambda i: i["badge"].get("result_id"),
        )
        assert shown == {
            n: (s["now"] or s["latest"] or {}).get("result_id")
            for n, s in by_name.items()
        }
        preview = await previewed(client, dataset, {"image_ids": list(ids.values())})
        said = per_image(
            preview["images"], lambda i: (i["result"], i["adopted"]), lambda i: i["id"]
        )
        assert said == {
            "a": ("detected", "result"),
            "b": ("detected", "result"),
            "c": ("detected", "excluded"),
            "d": ("stale", "stale"),
            "e": ("failed", "none"),
            "f": ("pending", "none"),
        }
        ok = query(db, dataset, "image", {"result": "ok"})["items"]
        assert sorted(per_image(ok, lambda _i: True)) == ["a", "b", "c"]

    scenario(tmp_path, monkeypatch, body)


def test_images_are_judged_by_the_plan_they_are_looked_at_with(tmp_path, monkeypatch):
    # User 2026-10-22: making another plan, the images still showed the latest version's
    # results ("now" was the latest version's, chosen inside the states; definition 35.7).
    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset)  # a.png succeeds by version 1
        other = [{"name": "square", "shape": "bbox", "attributes": []}]
        written = await client.put(
            f"/v1/datasets/{dataset}/drafts/instruction",
            json={"text": "四角", "label_definitions": other},
        )
        assert written.status_code == 200, written.text
        db = app.state.db

        def image(where):
            items = query(db, dataset, "image", where)["items"]
            return next(i for i in items if i["image"]["id"] == ids["a.png"])

        # By the plan now (the draft): version 1's result is of another requirement.
        by_draft = image({})
        assert by_draft["badge"]["kind"] == "stale"
        assert by_draft["annotations"] == []
        by_version = image({"revision": 1})
        assert by_version["badge"]["kind"] == "result"
        assert by_version["annotations"]

    scenario(tmp_path, monkeypatch, body)


def test_images_are_judged_by_a_blank_plan_before_another_is_begun(
    tmp_path, monkeypatch
):
    # User 2026-10-24: talking of another plan not begun yet, the images showed the plan now's
    # results (no plan not begun could be named; definition 49.1).
    from agent_app.errors import ApiError

    async def body(app, client, dataset, ids):
        await run_once(
            client, app, dataset
        )  # a.png succeeds by version 1, the plan now
        db = app.state.db

        def image(where):
            items = query(db, dataset, "image", where)["items"]
            return next(i for i in items if i["image"]["id"] == ids["a.png"])

        assert image({})["annotations"]
        blank = image({"blank": True})
        assert blank["badge"]["kind"] == "stale"
        assert blank["annotations"] == []
        try:
            query(db, dataset, "image", {"blank": True, "revision": 1})
        except ApiError as exc:
            assert exc.status == 422
        else:
            raise AssertionError("a blank plan with a version was taken")

    scenario(tmp_path, monkeypatch, body)


def test_a_run_of_another_plan_shows_its_images_by_that_plan(tmp_path, monkeypatch):
    # User 2026-10-22: a decision's preview judged the images by the latest version, so a trial
    # of a draft with another requirement counted version 1's results (definition 36.1).
    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset)  # a.png succeeds by version 1
        other = [{"name": "square", "shape": "bbox", "attributes": []}]
        written = await client.put(
            f"/v1/datasets/{dataset}/drafts/instruction",
            json={"text": "四角", "label_definitions": other},
        )
        write = written.json()["write_id"]
        args = {"image_ids": [ids["a.png"]], "trial": True}
        by_draft = await previewed(client, dataset, {**args, "draft_write_id": write})
        assert by_draft["images"][0]["result"] == "stale"
        by_version = await previewed(client, dataset, {**args, "revision": 1})
        assert by_version["images"][0]["adopted"] == "result"

    scenario(tmp_path, monkeypatch, body)


def test_an_annotation_of_other_criteria_is_not_done_but_still_used(
    tmp_path, monkeypatch
):
    # Definition 85.4 (2026-10-30 review 3): "only closed boxes" kept counting what was
    # annotated for "every box"; a run by the plan is made by its criteria, not checked.
    from agent_app.image_state import state_counts
    from agent_app.instructions import criteria_key, latest_revision, version_payload

    async def body(app, client, dataset, ids):
        db = app.state.db
        a = ids["a.png"]
        await run_once(client, app, dataset, image_ids=[a])
        _, states = image_states(db, dataset, *latest_basis(db, dataset))
        assert (states[a]["now"]["criteria"], states[a]["now"]["checked"]) == (
            "this",
            False,
        )
        # A person's fix is made by a person: checked by its version's criteria.
        draft = f"/v1/datasets/{dataset}/images/{a}/drafts/fix"
        box = {"label": "circle", "geometry": {"type": "bbox", "xywh": [1, 1, 5, 5]}}
        fixed = {"from_result_id": states[a]["now"]["result_id"], "annotations": [box]}
        await client.put(draft, json=fixed)
        assert (await client.post(draft + "/save")).status_code == 201
        _, states = image_states(db, dataset, *latest_basis(db, dataset))
        assert states[a]["now"]["checked"] is True
        # More left out: other criteria; not done by them, still used for training.
        plan = {
            "text": "円を囲む。",
            "label_definitions": DEFINITIONS,
            "leave_out": ["欠けた円"],
        }
        save_version(db, dataset, plan)
        _, states = image_states(db, dataset, *latest_basis(db, dataset))
        counts = state_counts(states)
        assert states[a]["now"]["criteria"] == "other"
        assert (counts["done"], counts["other"], counts["used"]) == (0, 1, 1)
        # The run's box says so (definition 85.6).
        shown = await previewed(client, dataset, {"image_ids": [a]})
        assert shown["card"]["happens"]["other"] == {"images": 1, "in_run": 1}
        # The references are a way of drawing, not the criteria.
        saved = version_payload(db, dataset, latest_revision(db, dataset))
        drawn = {**saved, "references": [{"result_id": "r"}]}
        assert criteria_key(drawn) == criteria_key(saved)

    scenario(tmp_path, monkeypatch, body)
