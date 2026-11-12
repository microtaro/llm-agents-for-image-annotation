"""A person's fix, the result a person chose for training, and fixing the training data
(types design 7)."""

import test_runs
from agent_app.run_inputs import last_choice
from test_runs import CIRCLE, DEFINITIONS, run_once, save_version, scenario


def _box(xywh):
    return {"label": "circle", "geometry": {"type": "bbox", "xywh": xywh}}


async def _used(client, dataset):
    items = (await client.get(f"/v1/datasets/{dataset}/adoption")).json()["items"]
    return {i["image_id"]: i for i in items}


def test_a_dataset_a_person_fixed_is_deleted(tmp_path, monkeypatch):
    # User 2026-10-27: deleting it failed (a fix points at the result it was fixed from, and the
    # fix's result at the fix); a fix of the fix too.
    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        await run_once(client, app, dataset)
        draft = f"/v1/datasets/{dataset}/images/{a}/drafts/fix"
        for _ in range(2):
            result = (await _used(client, dataset))[a]["result_id"]
            await client.put(
                draft,
                json={"from_result_id": result, "annotations": [_box([1, 1, 5, 5])]},
            )
            assert (await client.post(draft + "/save")).status_code == 201
        gone = await client.delete(f"/v1/datasets/{dataset}")
        assert gone.status_code == 200, gone.text
        assert (await client.get(f"/v1/datasets/{dataset}")).status_code == 404

    scenario(tmp_path, monkeypatch, body)


def test_a_number_taken_out_of_a_fix_is_not_given_again(tmp_path, monkeypatch):
    # User 2026-10-27 (Sol's test): the highest number taken out in a fix was given to the
    # object added; a fix carries on the numbers of the result it was fixed from.
    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        await run_once(client, app, dataset)
        draft = f"/v1/datasets/{dataset}/images/{a}/drafts/fix"

        async def fix(annotations):
            result = (await _used(client, dataset))[a]["result_id"]
            await client.put(
                draft, json={"from_result_id": result, "annotations": annotations}
            )
            assert (await client.post(draft + "/save")).status_code == 201
            now = (await _used(client, dataset))[a]["result_id"]
            got = (await client.get(f"/v1/results/{now}")).json()["annotations"]
            return sorted(x["number"] for x in got)

        # The AI's circle 1 taken out and three added: 2, 3, 4.
        first = await fix(
            [_box([1, 1, 5, 5]), _box([10, 1, 5, 5]), _box([20, 1, 5, 5])]
        )
        assert first == [2, 3, 4]
        # The highest (4) taken out and one added: 5, not 4 again.
        kept = [
            {**_box([1, 1, 5, 5]), "number": 2},
            {**_box([10, 1, 5, 5]), "number": 3},
        ]
        assert await fix([*kept, _box([30, 1, 5, 5])]) == [2, 3, 5]

    scenario(tmp_path, monkeypatch, body)


def test_a_fix_of_an_earlier_requirement_says_so(tmp_path, monkeypatch):
    # 2026-10-30 review: every record but a run said it was not of an earlier requirement,
    # whatever it was of.
    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        await run_once(client, app, dataset)
        result = (await _used(client, dataset))[a]["result_id"]
        draft = f"/v1/datasets/{dataset}/images/{a}/drafts/fix"
        fixed = {"from_result_id": result, "annotations": [_box([1, 1, 5, 5])]}
        await client.put(draft, json=fixed)
        fix_id = (await client.post(draft + "/save")).json()["fix_id"]
        square = {"name": "square", "shape": "bbox", "attributes": []}
        plan = {"text": "囲む", "label_definitions": [*DEFINITIONS, square]}
        save_version(app.state.db, dataset, plan)
        record = (await client.get(f"/v1/records/{fix_id}")).json()
        assert (record["earlier"], record["usable"]) == (True, False)

    scenario(tmp_path, monkeypatch, body)


def test_a_fix_is_kept_when_the_image_is_done_again(tmp_path, monkeypatch):
    # Issue #5-2, definition 10 (user 2026-10-16): a newer success does not replace a person's
    # fix or choice; it is said (newer). Every choice is kept as a decision added (#5-3).
    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        first = await run_once(client, app, dataset)
        result = (await _used(client, dataset))[a]["result_id"]
        draft = f"/v1/datasets/{dataset}/images/{a}/drafts/fix"
        written = await client.put(
            draft, json={"from_result_id": result, "annotations": [_box([1, 1, 5, 5])]}
        )
        assert written.status_code == 200, written.text
        saved = await client.post(draft + "/save")
        assert saved.status_code == 201, saved.text
        # The undo chooses again the result used before the fix (definition 19.2).
        assert saved.json()["before"] == result
        # A person's fix is not a run (issue #4 F-12, definition 21.4): a record of its own,
        # numbered after the run it fixed.
        fix_id = saved.json()["fix_id"]
        runs = (await client.get(f"/v1/datasets/{dataset}/runs")).json()["runs"]
        assert fix_id not in [r["id"] for r in runs]
        record = (await client.get(f"/v1/records/{fix_id}")).json()
        assert (record["kind"], record["number"]) == ("fix", first["number"] + 1)
        # No draft any more reads as none, not a 404 (user 2026-10-27: one at every loupe).
        gone = await client.get(draft)
        assert (gone.status_code, gone.json()) == (200, None)
        stopped = await client.delete(draft)
        assert (stopped.status_code, stopped.json()) == (200, {"deleted": False})
        used = (await _used(client, dataset))[a]
        assert (used["result_id"], used["by"], used["picked"]) == (
            saved.json()["result_id"],
            "human",
            True,
        )
        # The next AI run does not go on with the fix's "model".
        assert last_choice(app.state.db, dataset)[0] != "human"
        # Deciding to do it again says the fix stays (definition 19.6).
        shown = await client.post(
            f"/v1/datasets/{dataset}/proposals/preview",
            json={
                "tool": "run_start",
                "args": {"image_ids": [a], "budget_per_image_usd": "1"},
                "title": "流す",
                "reason": "r",
            },
        )
        happens = shown.json()["preview"]["card"]["happens"]
        assert (happens["kept"], happens["used_after"]) == ([a], [])
        # The image done again: the fix stays, and a newer one is said.
        again = await run_once(client, app, dataset, image_ids=[a])
        used = (await _used(client, dataset))[a]
        assert (used["result_id"], used["by"], used["newer"]) == (
            saved.json()["result_id"],
            "human",
            True,
        )
        # The loupe's records say which one training uses (user 2026-10-13: look, then choose).
        records = (
            await client.get(f"/v1/datasets/{dataset}/images/{a}/results")
        ).json()["results"]
        assert [r["result_id"] for r in records if r["used"]] == [
            saved.json()["result_id"]
        ]
        # Back to the rule: the newest result.
        await client.delete(f"/v1/datasets/{dataset}/images/{a}/adoption")
        assert (await _used(client, dataset))[a]["run_id"] == again["id"]
        # The first record's images use its results again (only those images).
        assert (await client.post(f"/v1/runs/{first['id']}/use")).json()["images"] == 1
        assert (await _used(client, dataset))[a]["run_id"] == first["id"]
        await client.post(f"/v1/datasets/{dataset}/adoption/latest")
        assert (await _used(client, dataset))[a]["run_id"] == again["id"]
        # Who chose what, and when, stays (nothing written over): the fix made, then a
        # person's decisions (definition 21.3).
        rows = app.state.db.execute(
            "SELECT u.kind, d.decided_by FROM uses u LEFT JOIN decisions d"
            " ON d.id=u.decision_id WHERE u.image_id=? ORDER BY u.id",
            (a,),
        )
        assert [(r["kind"], r["decided_by"]) for r in rows] == [
            ("fix", None),
            ("rule", "outside"),
            ("pick", "outside"),
            ("rule", "outside"),
        ]
        # A fix of a result of another image is refused.
        wrong = await client.post(
            f"/v1/datasets/{dataset}/images/{ids['fail.png']}/fixes",
            json={"from_result_id": result, "annotations": [_box(CIRCLE["xywh"])]},
        )
        assert wrong.status_code == 422

    scenario(tmp_path, monkeypatch, body)


def test_an_earlier_record_is_made_the_annotation_again(tmp_path, monkeypatch):
    """User 2026-10-16: in the loupe of annotating, choosing a record makes it the annotation
    and training uses it; going back and forth makes no record. A left-out image stays left
    out (definition 19.4: choosing does not change whether the image is used)."""

    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        await run_once(client, app, dataset)
        first = (await _used(client, dataset))[a]["result_id"]
        await run_once(client, app, dataset)
        second = (await _used(client, dataset))[a]["result_id"]
        records = f"/v1/datasets/{dataset}/images/{a}/results"
        count = len((await client.get(records)).json()["results"])

        async def switch(result_id):
            done = await client.post(
                f"/v1/datasets/{dataset}/images/{a}/switch",
                json={"result_id": result_id},
            )
            assert done.status_code == 200, done.text
            page = await client.get(f"/v1/datasets/{dataset}/gallery?view=run")
            card = next(i for i in page.json()["items"] if i["image"]["id"] == a)
            assert card["badge"]["result_id"] == result_id
            assert (await _used(client, dataset))[a]["result_id"] == result_id
            return done.json()["before"]

        assert await switch(first) is None
        assert await switch(second) == first
        assert len((await client.get(records)).json()["results"]) == count
        await client.post(f"/v1/datasets/{dataset}/images/{a}/exclude")
        await client.post(
            f"/v1/datasets/{dataset}/images/{a}/switch", json={"result_id": first}
        )
        assert (await _used(client, dataset))[a]["source"] == "excluded"

    scenario(tmp_path, monkeypatch, body)


def test_a_left_out_image_chosen_for_training_is_used(tmp_path, monkeypatch):
    """Found 2026-10-16: a person chose a record of a left-out image for training; the image
    showed it, but training kept the one before and the ring stayed empty."""

    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        await run_once(client, app, dataset)
        first = (await _used(client, dataset))[a]["result_id"]
        fix = {"from_result_id": first, "annotations": []}
        made = (
            await client.post(f"/v1/datasets/{dataset}/images/{a}/fixes", json=fix)
        ).json()
        await client.post(f"/v1/datasets/{dataset}/images/{a}/exclude")
        chosen = await client.put(
            f"/v1/datasets/{dataset}/images/{a}/adoption",
            json={"result_id": made["result_id"]},
        )
        assert chosen.status_code == 200, chosen.text
        assert (await _used(client, dataset))[a]["result_id"] == made["result_id"]

    scenario(tmp_path, monkeypatch, body)


def test_a_left_out_image_still_shows_its_annotation(tmp_path, monkeypatch):
    """User 2026-10-16: left out of training, the gallery showed not even its annotation; it
    shows the record it would use once taken back."""

    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        await run_once(client, app, dataset)
        used = (await _used(client, dataset))[a]["result_id"]
        await client.post(f"/v1/datasets/{dataset}/images/{a}/exclude")
        page = await client.get(f"/v1/datasets/{dataset}/gallery?view=production")
        card = next(i for i in page.json()["items"] if i["image"]["id"] == a)
        assert card["badge"]["kind"] == "excluded" and card["badge"]["ran"]
        assert card["badge"]["result_id"] == used and card["annotations"]
        assert card["badge"]["by"] == "ai"

    scenario(tmp_path, monkeypatch, body)


def test_a_run_that_failed_after_a_success_shows_on_the_card(tmp_path, monkeypatch):
    """User 2026-10-16: the card shows the image's last success, so a run that failed after
    it was hidden; how many failed on which version, and why, are said beside it."""

    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        await run_once(client, app, dataset)
        monkeypatch.setattr(
            test_runs.runs_module,
            "infer",
            test_runs.fake_inference(app, fail_names=("a.png", "fail.png")),
        )
        await run_once(client, app, dataset)
        for view in ("run", "adoption"):
            page = await client.get(f"/v1/datasets/{dataset}/gallery?view={view}")
            card = next(i for i in page.json()["items"] if i["image"]["id"] == a)
            assert card["badge"]["kind"] in ("detected", "result")
            failures = card["badge"]["failures"]
            assert failures["parts"] == [{"revision": 1, "count": 1}]
            assert "Observed failure" in failures["reason"]

    scenario(tmp_path, monkeypatch, body)


def test_a_record_is_only_used_never_taken_back_to_the_results_before(
    tmp_path, monkeypatch
):
    # Definition 54 (user 2026-10-27): "not used" took each image back to the result before the
    # record, which differed per image and was not seen before pressing. A record is used, or
    # another one is chosen by name; the screen's way and the decision's are gone.
    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset)
        second = await run_once(client, app, dataset)
        gone = await client.post(f"/v1/runs/{second['id']}/revert")
        assert gone.status_code in (404, 405)
        box = {
            "tool": "mark",
            "args": {"target": "run", "excluded": True, "run_id": second["id"]},
            "title": "t",
            "reason": "r",
        }
        refused = await client.post(f"/v1/datasets/{dataset}/proposals", json=box)
        assert refused.status_code == 422, refused.text
        box["args"]["excluded"] = False
        made = await client.post(f"/v1/datasets/{dataset}/proposals", json=box)
        assert made.status_code == 201, made.text

    scenario(tmp_path, monkeypatch, body)


def test_the_training_data_is_fixed_as_numbered_versions(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset)
        path = f"/v1/datasets/{dataset}/training"
        before = (await client.get(path)).json()
        assert (before["next"], before["used"], len(before["changed"])) == (1, 1, 1)
        fixed = await client.post(path, json={"note": "最初"})
        assert fixed.status_code == 201, fixed.text
        assert (fixed.json()["last"]["number"], fixed.json()["changed"]) == (1, [])
        await client.post(f"/v1/datasets/{dataset}/images/{ids['a.png']}/exclude")
        after = (await client.get(path)).json()
        assert [c["image_id"] for c in after["changed"]] == [ids["a.png"]]
        assert after["parts"]["excluded"] == 1 and after["next"] == 2
        # Only a person fixes it.
        refused = await client.post(
            path, json={}, headers={"X-Annotation-Agent": "steward"}
        )
        assert refused.status_code == 403

    scenario(tmp_path, monkeypatch, body)


def test_a_recorded_version_holds_what_it_held(tmp_path, monkeypatch):
    # Sol 2026-10-13: version 1's [Open] showed what training gets now, not what was recorded.
    # User 2026-10-15: no fixing, so a later change keeps the dataset complete.
    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        await run_once(client, app, dataset)
        await client.post(f"/v1/datasets/{dataset}/images/{ids['fail.png']}/exclude")
        await client.post(f"/v1/datasets/{dataset}/training", json={})
        progress = f"/v1/datasets/{dataset}/progress"
        assert (await client.get(progress)).json()["overall"]["kind"] == "complete"
        first = (await _used(client, dataset))[a]["result_id"]
        await client.post(
            f"/v1/datasets/{dataset}/images/{a}/fixes",
            json={"from_result_id": first, "annotations": [_box([1, 1, 5, 5])]},
        )
        assert (await client.get(progress)).json()["overall"]["kind"] == "complete"
        version = (await client.get(f"/v1/datasets/{dataset}/objects/snapshot")).json()
        held = {i["image_id"]: i["result"] for i in version["items"][0]["items"]}
        assert held[a]["result_id"] == first and held[a]["by"] == "ai"

    scenario(tmp_path, monkeypatch, body)


def test_a_persons_fix_is_seen_as_any_result(tmp_path, monkeypatch):
    # Review 2026-10-28 (B#12, C#3): a worker looking at a person's fix (or a record taken in)
    # failed: its colors were read from the run the result came from, and a fix has none.
    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        await run_once(client, app, dataset)
        result = (await _used(client, dataset))[a]["result_id"]
        draft = f"/v1/datasets/{dataset}/images/{a}/drafts/fix"
        await client.put(
            draft, json={"from_result_id": result, "annotations": [_box([1, 1, 5, 5])]}
        )
        fixed = (await client.post(draft + "/save")).json()["result_id"]
        seen = await client.post(f"/v1/results/{fixed}/views", json={"overlay": True})
        assert seen.status_code == 200, seen.text

    scenario(tmp_path, monkeypatch, body)


def test_what_other_datasets_annotated_is_a_persons_fix_over_the_ai(
    tmp_path, monkeypatch
):
    # Found 2026-10-29: what other datasets annotated these images for (the interview's past
    # requirements) took the newest way's AI result over a person's later fix of it; each
    # image's annotation is read as its gallery shows it (image_state).
    async def body(app, client, dataset, ids):
        a = ids["a.png"]
        await run_once(client, app, dataset)
        first = (await _used(client, dataset))[a]["result_id"]
        fix = {"from_result_id": first, "annotations": []}
        await client.post(f"/v1/datasets/{dataset}/images/{a}/fixes", json=fix)
        other = await client.post(
            "/v1/datasets", json={"name": "他", "purpose": "円", "image_ids": [a]}
        )
        past = await client.get(f"/v1/datasets/{other.json()['id']}/plan/past")
        assert past.json()["requirements"][0]["by_image"][a] == []

    scenario(tmp_path, monkeypatch, body)
