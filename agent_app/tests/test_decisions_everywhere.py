"""Every decision a worker can make ready (definition 22): one test per thing found (issue #3
U-03, U-12, the reception refusing to make a dataset on 2026-10-15, #5-14, #4 F-16)."""

import asyncio
import json

from PIL import Image
from test_drafts_and_ai import mcp
from test_runs import run_once, scenario

from agent_app import agent_answer

PERSON = {"X-Actor": "ui"}


def _worker(dataset, agent="steward"):
    return {
        "X-Annotation-Agent": agent,
        "X-Annotation-Dataset": dataset,
    }


RECEPTION = {
    "X-Annotation-Agent": "reception",
    "X-Annotation-Dataset": "",
}


async def _made(worker, tool, args, title="t"):
    got = await worker.call_tool(
        "proposal_make",
        {"tool": tool, "args": args, "title": title, "reason": "r"},
    )
    assert not got.is_error, got.structured_content
    return got.structured_content["data"]


def _decision_of(app, box_id):
    return app.state.db.one("SELECT * FROM decisions WHERE proposal_id=?", (box_id,))


def test_a_worker_makes_the_decisions_of_its_dataset_ready(tmp_path, monkeypatch):
    # Issue #3 U-03: a worker could propose only a run and a mark; taking out an image,
    # renaming a label or choosing a result it could neither do nor propose.
    async def body(app, client, dataset, ids):
        made = await run_once(client, app, dataset, image_ids=[ids["a.png"]])
        results = (await client.get(f"/v1/runs/{made['id']}/results")).json()
        result = results["results"][0]["result_id"]
        async with mcp(app, _worker(dataset)) as worker:
            # Not its own to do: the refusal says the way that is open.
            direct = await worker.call_tool(
                "dataset_remove_images", {"image_ids": ["fail.png"]}
            )
            assert direct.structured_content["error"]["code"] == "agent_tool"
            assert "proposal_make" in direct.structured_content["next_actions"][0]
            removing = await _made(
                worker, "dataset_remove_images", {"image_ids": ["fail.png"]}
            )
            # A label is named in the plan, so it is renamed there by the steward (user
            # 2026-10-28; until then only the reception could, the label being the library's).
            renaming = await _made(
                worker, "label_rename", {"from": "circle", "to": "丸"}
            )
            picking = await _made(
                worker, "pick", {"image_id": "a.png", "result_id": result}
            )
            # Making a dataset is the library's: the reception's.
            library = await worker.call_tool(
                "proposal_make",
                {
                    "tool": "dataset_create",
                    "args": {"name": "n", "purpose": "p", "paths": [str(tmp_path)]},
                    "title": "t",
                    "reason": "r",
                },
            )
            assert library.structured_content["error"]["code"] == "library_decision"
        # The label is one for every dataset: the box says how many plans the name changes.
        assert renaming["preview"]["datasets"] == 1
        assert removing["preview"]["images"][0]["name"] == "fail.png"
        assert (renaming["preview"]["from"], renaming["preview"]["to"]) == (
            "circle",
            "丸",
        )
        assert picking["step"] == "drop"
        # A renamed label is the same label (definition 23): the pick stays after the rename.
        for box, kind, asker in (
            (removing, "images", "agent:steward"),
            (renaming, "label", "agent:steward"),
            (picking, "use", "agent:steward"),
        ):
            done = await client.post(f"/v1/proposals/{box['id']}/apply", headers=PERSON)
            assert done.status_code == 200, done.text
            decision = _decision_of(app, box["id"])
            assert (
                decision["kind"],
                decision["decided_by"],
                decision["requested_by"],
            ) == (kind, "person", asker)
        db = app.state.db
        removed = db.one(
            "SELECT decision_id FROM dataset_image_removals WHERE image_id=?",
            (ids["fail.png"],),
        )
        assert removed["decision_id"] == _decision_of(app, removing["id"])["id"]
        version = db.one(
            "SELECT decision_id FROM instructions WHERE dataset_id=? ORDER BY revision"
            " DESC LIMIT 1",
            (dataset,),
        )
        assert version["decision_id"] == _decision_of(app, renaming["id"])["id"]

    scenario(tmp_path, monkeypatch, body)


def test_the_reception_makes_a_dataset_ready_at_the_library(tmp_path, monkeypatch):
    # 2026-10-15: asked "make a dataset", the reception said no (it had no tools), while the
    # library on the right makes one. Its longer turn proposes it; a person decides it in the
    # library's talk; the dataset holds the decision, which is of no dataset.
    folder = tmp_path / "new"
    folder.mkdir()
    Image.new("RGB", (30, 20), (5, 6, 7)).save(folder / "n1.png")

    async def body(app, client, dataset, ids):
        async def turn(key, **given):
            # A kept CLI names its chat; the server finds the answer going in it (27.4).
            chat = str(key[2])
            async with mcp(app, {**RECEPTION, "X-Annotation-Chat": chat}) as r:
                names = {t.name for t in (await r.list_tools()).tools}
                assert {"read", "look", "proposal_make"} <= names
                # At the library, a dataset's work waits for the dataset to be open.
                inside = await r.call_tool(
                    "look", {"type": "image", "id": ids["a.png"]}
                )
                assert inside.structured_content["error"]["code"] == "agent_scope"
                await _made(
                    r,
                    "dataset_create",
                    {"name": "新しい", "purpose": "試す", "paths": [str(folder)]},
                    "「新しい」を作る",
                )
            return (
                {
                    "kind": "answer",
                    "message": "作る決定を出しました。",
                    "question": None,
                    "open": None,
                    "handoff": None,
                    "boxes": [],
                },
                None,
                None,
            )

        settings = lambda *_: {"model": "claude-haiku-5-5", "effort": "low"}
        monkeypatch.setattr(agent_answer, "selected_execution_settings", settings)
        monkeypatch.setattr(app.state.jobs.residents, "turn", turn)
        asked = await client.post(
            "/v1/library/agents/reception/messages",
            json={"text": "new フォルダでデータセットを作って"},
        )
        assert asked.status_code == 202, asked.text
        for _ in range(500):
            got = (await client.get("/v1/library/agents/reception/events")).json()
            if not got["answering"]:
                break
            await asyncio.sleep(0.01)
        line = got["events"][-1]
        assert line["kind"] == "ai", line
        (box_id,) = line["data"]["proposal_ids"]
        box = (await client.get(f"/v1/proposals/{box_id}")).json()
        assert (box["dataset_id"], box["agent"], box["preview"]["found"]) == (
            None,
            "reception",
            1,
        )
        listed = (await client.get("/v1/library/proposals")).json()["proposals"]
        assert [p["id"] for p in listed] == [box_id]
        done = await client.post(f"/v1/proposals/{box_id}/apply", headers=PERSON)
        assert done.status_code == 200, done.text
        made = done.json()["outcome"]
        decision = _decision_of(app, box_id)
        assert (decision["dataset_id"], decision["kind"]) == (None, "dataset")
        row = app.state.db.one(
            "SELECT decision_id FROM datasets WHERE id=?", (made["id"],)
        )
        assert row["decision_id"] == decision["id"]
        events = (await client.get("/v1/library/agents/reception/events")).json()[
            "events"
        ]
        assert events[-1]["data"]["note"] == "box_applied"

    scenario(tmp_path, monkeypatch, body)


def test_the_reception_works_in_the_dataset_it_names_at_the_library(
    tmp_path, monkeypatch
):
    # 2026-10-28 (definition 63): opening a dataset makes the left its steward (35.2), so the
    # reception never had one open and refused a dataset's work asked of it ("open it");
    # a decision names its dataset, the screen is a way of seeing: named, it is done there.
    async def body(app, client, dataset, ids):
        async with mcp(app, RECEPTION) as r:
            seen = await r.call_tool(
                "look", {"type": "image", "id": "a.png", "dataset_id": dataset}
            )
            assert not seen.is_error, seen.structured_content
            made = await r.call_tool(
                "proposal_make",
                {
                    "dataset_id": dataset,
                    "tool": "mark",
                    "args": {"target": "image", "image_id": "a.png", "excluded": True},
                    "title": "a を外す",
                    "reason": "r",
                },
            )
            assert not made.is_error, made.structured_content
            box = made.structured_content["data"]
            row = app.state.db.one(
                "SELECT dataset_id, agent, args_json FROM proposals WHERE id=?",
                (box["id"],),
            )
            assert (row["dataset_id"], row["agent"]) == (dataset, "reception")
            assert json.loads(row["args_json"])["image_id"] == ids["a.png"]
            # Named, it is that dataset's only: another's image is no image of it, as for a
            # steward (datasets.image_id_of).
            path = tmp_path / "other.png"
            Image.new("RGB", (50, 40), (1, 2, 3)).save(path)
            other = (
                await client.post("/v1/images/import", json={"paths": [str(path)]})
            ).json()["images"][0]["id"]
            outside = await r.call_tool(
                "look", {"type": "image", "id": other, "dataset_id": dataset}
            )
            assert outside.structured_content["error"]["code"] == "invalid_input"

    scenario(tmp_path, monkeypatch, body)


def test_a_tools_hints_say_what_it_does(tmp_path, monkeypatch):
    # Issue #3 U-12: making a proposal was as destructive as deleting a dataset.
    async def body(app, client, dataset, ids):
        async with mcp(app) as outside:
            hints = {t.name: t.annotations for t in (await outside.list_tools()).tools}
        assert not hints["proposal_make"].destructive_hint
        assert hints["dataset_delete"].destructive_hint
        assert hints["read"].read_only_hint
        assert not hints["run_start"].destructive_hint

    scenario(tmp_path, monkeypatch, body)


def test_a_name_of_two_images_says_which_is_wanted(tmp_path, monkeypatch):
    # Issue #4 F-16: images are named by name, and two of the same name were taken silently
    # as the later one in one place and refused in another.
    async def body(app, client, dataset, ids):
        twins = []
        for folder in ("x", "y"):
            (tmp_path / folder).mkdir()
            path = tmp_path / folder / "same.png"
            Image.new("RGB", (20, 20), (len(folder) * 9, len(twins) * 50, 3)).save(path)
            twins.append(
                (
                    await client.post("/v1/images/import", json={"paths": [str(path)]})
                ).json()["images"][0]["id"]
            )
        await client.post(f"/v1/datasets/{dataset}/images", json={"image_ids": twins})
        shown = await client.get(
            f"/v1/datasets/{dataset}/objects/image", params={"ids": "same.png"}
        )
        assert shown.status_code == 422
        assert "give the id" in json.dumps(shown.json())
        async with mcp(app, _worker(dataset)) as worker:
            got = await worker.call_tool("look", {"type": "image", "id": "same.png"})
        assert got.structured_content["error"]["code"] == "invalid_input"

    scenario(tmp_path, monkeypatch, body)


def test_images_imported_before_keep_their_origin_and_import_at_once(
    tmp_path, monkeypatch
):
    # Found 2026-10-26 (definition 52): asked to make a dataset of a folder imported before as
    # made images, the reception's first box was refused every time (the import asked for
    # their origin again), and the screen left them out.
    folder = tmp_path / "made"
    folder.mkdir()
    Image.new("RGB", (20, 20), (90, 1, 1)).save(folder / "m.png")

    async def body(app, client, dataset, ids):
        imported = await client.post(
            "/v1/images/import",
            json={
                "paths": [str(folder)],
                "origin": {"kind": "generated", "how": {"tool": "test"}},
            },
        )
        assert imported.status_code == 200, imported.text
        box = {
            "tool": "dataset_create",
            "args": {"name": "n", "purpose": "p", "paths": [str(folder)]},
            "title": "t",
            "reason": "r",
        }
        made = await client.post("/v1/library/proposals", json=box)
        assert made.status_code == 201, made.text
        assert (made.json()["preview"]["found"], made.json()["preview"]["kept"]) == (
            1,
            1,
        )
        done = await client.post(
            f"/v1/proposals/{made.json()['id']}/apply", headers=PERSON
        )
        assert done.status_code == 200, done.text
        image_id = imported.json()["images"][0]["id"]
        db = app.state.db
        assert (
            db.one(
                "SELECT count(*) FROM dataset_images d JOIN datasets s ON s.id=d.dataset_id"
                " WHERE s.name='n' AND d.image_id=?",
                (image_id,),
            )[0]
            == 1
        )
        row = db.one("SELECT origin, origin_json FROM images WHERE id=?", (image_id,))
        assert (row["origin"], json.loads(row["origin_json"])) == (
            "generated",
            {"tool": "test"},
        )

    scenario(tmp_path, monkeypatch, body)
