"""A dataset's sheets: every image, 16 a page, in an order spread over the folders (definition
42)."""

import asyncio
import json

import httpx
from agent_app.app import create_app
from agent_app.run_inputs import start_targets
from agent_app.sheets import dataset_order, spread
from PIL import Image
from test_agents import _agent_headers
from test_drafts_and_ai import mcp
from test_runs import run_once
from test_runs import scenario as run_scenario


def scene(tmp_path, body, folders):
    """Run body(app, client, dataset, ids) with a dataset of these folders' images, in order
    (folders: name -> count; ids: each folder's image ids in its order)."""

    async def main():
        app = create_app(tmp_path / "sheets.db")
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
            ) as client,
        ):
            ids = {}
            for shade, (folder, count) in enumerate(folders.items()):
                (tmp_path / folder).mkdir()
                for i in range(count):
                    color = (i * 9, shade * 90, 40)
                    Image.new("RGB", (60, 40), color).save(
                        tmp_path / folder / f"{folder}{i:03}.png"
                    )
                imported = await client.post(
                    "/v1/images/import", json={"paths": [str(tmp_path / folder)]}
                )
                ids[folder] = [i["id"] for i in imported.json()["images"]]
            dataset = (
                await client.post(
                    "/v1/datasets",
                    json={
                        "name": "動物",
                        "purpose": "種類を見る",
                        "image_ids": [i for f in ids.values() for i in f],
                    },
                )
            ).json()["id"]
            await body(app, client, dataset, ids)

    asyncio.run(main())


def test_the_sheets_show_every_image_and_the_workers_see_them(tmp_path):
    # User 2026-10-23: a dataset of ten kinds of animals showed its first 16 images only, and no
    # worker could see them; the reception should too.
    async def body(app, client, dataset, ids):
        path = f"/v1/datasets/{dataset}/sheet"
        first, second = [
            (await client.get(path, params={"page": page})).json() for page in (1, 2)
        ]
        shown = [t["image_id"] for s in (first, second) for t in s["tiles"]]
        assert sorted(shown) == sorted(ids["a"] + ids["b"])
        assert (first["pages"], first["count"], len(first["tiles"])) == (2, 20, 16)
        # The first page is taken from both folders and from far into each.
        assert set(ids["b"]) <= set(shown[:16]) and ids["a"][13] in shown[:16]
        assert (await client.get(path, params={"page": 3})).status_code == 422
        reception = {"X-Annotation-Agent": "reception"}
        async with mcp(app, reception) as worker:
            seen = await worker.call_tool(
                "look", {"type": "dataset", "id": dataset, "page": 2}
            )
        assert seen.structured_content["ok"], seen.structured_content
        data = seen.structured_content["data"]
        assert data["page"] == 2 and data["tiles"][0]["name"].endswith(".png")
        assert [c.type for c in seen.content].count("image") == 1

    scene(tmp_path, body, {"a": 15, "b": 5})


def test_the_sheets_group_by_the_folders_the_card_counts(tmp_path):
    # 2026-10-30 (fact inventory 3): the card counted the folder the dataset took each image
    # from, the sheets grouped by the image's first file, another folder for an image imported
    # from two.
    async def main():
        app = create_app(tmp_path / "folders.db")
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
            ) as client,
        ):
            (tmp_path / "a").mkdir()
            (tmp_path / "b").mkdir()
            for i in range(4):
                Image.new("RGB", (60, 40), (i * 50, 20, 40)).save(
                    tmp_path / "b" / f"b{i}.png"
                )
            for i in (0, 3):
                (tmp_path / "a" / f"a{i}.png").write_bytes(
                    (tmp_path / "b" / f"b{i}.png").read_bytes()
                )
            await client.post(
                "/v1/images/import", json={"paths": [str(tmp_path / "a")]}
            )
            made = await client.post(
                "/v1/datasets",
                json={"name": "箱", "purpose": "見る", "paths": [str(tmp_path / "b")]},
            )
            dataset = made.json()["id"]
            card = (await client.get(f"/v1/datasets/{dataset}")).json()
            assert card["sources"] == [{"folder": str(tmp_path / "b"), "count": 4}]
            ids = [i["image_id"] for i in card["images"]]
            assert dataset_order(app.state.db, dataset) == spread({"b": ids})

    asyncio.run(main())


def test_a_trial_of_no_images_takes_images_spread_over_the_dataset(tmp_path):
    # User 2026-10-23: the samples were the first images, all of one kind.
    async def body(app, client, dataset, ids):
        taken = start_targets(app.state.db, dataset, None, True)
        order = ids["a"]
        assert taken == [order[0], order[10], order[5]]

    scene(tmp_path, body, {"a": 20})


def test_the_steward_sees_a_library_label_as_other_datasets_annotated_it(
    tmp_path, monkeypatch
):
    # User 2026-10-24: the steward asked "is it the same thing?" from a label's name only; the
    # label's sheet, on the left of that question, was the person's alone (definition 46).
    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset, image_ids=[ids["a.png"]], revision=1)
        label = next(
            x
            for x in (await client.get("/v1/labels")).json()["items"]
            if x["name"] == "circle"
        )
        async with mcp(app, _agent_headers(dataset)) as worker:
            seen = await worker.call_tool("look", {"type": "label", "id": label["id"]})
        assert seen.structured_content["ok"], seen.structured_content
        tiles = seen.structured_content["data"]["tiles"]
        assert [t["name"] for t in tiles] == ["a.png"]
        assert [c.type for c in seen.content].count("image") == 1

    run_scenario(tmp_path, monkeypatch, body)


def test_a_label_taken_out_of_a_plan_shows_none_of_its_results_any_more(
    tmp_path, monkeypatch
):
    # User 2026-10-29: a dataset that had named the wrong library label took it out of its plan;
    # its results, no image's annotation any more, still showed as the label's objects (the
    # list chose its own results, not each image's annotation now as the gallery shows it).
    from agent_app.sheets import label_objects
    from test_runs import save_version

    async def body(app, client, dataset, ids):
        db = app.state.db
        await run_once(client, app, dataset, image_ids=[ids["a.png"]], revision=1)
        circle = next(
            x
            for x in (await client.get("/v1/labels")).json()["items"]
            if x["name"] == "circle"
        )
        assert len(label_objects(db, circle["id"])) == 1
        plan = json.loads(
            db.one(
                "SELECT payload_json FROM instructions WHERE dataset_id=?"
                " ORDER BY revision DESC",
                (dataset,),
            )[0]
        )
        other = [
            {k: v for k, v in d.items() if k != "id"} | {"name": "丸"}
            for d in plan["label_definitions"]
        ]
        content = {"text": plan["text"], "label_definitions": other}
        await client.put(f"/v1/datasets/{dataset}/drafts/instruction", json=content)
        save_version(db, dataset, content)
        assert label_objects(db, circle["id"]) == []

    run_scenario(tmp_path, monkeypatch, body)


def test_workers_read_things_by_their_type_as_they_show_them(tmp_path, monkeypatch):
    # Definition 51 (user 2026-10-26): eleven tools read the plan, the datasets and the
    # labels, and which one to use was the worker's to guess; they read by type and
    # conditions now, as they show things, and at the library only the library's types.
    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset, image_ids=[ids["a.png"]], revision=1)
        async with mcp(app, {"X-Annotation-Agent": "reception"}) as reception:
            for kind in ("dataset", "label", "version"):
                got = await reception.call_tool("read", {"type": kind})
                assert got.structured_content["ok"], (kind, got.structured_content)
            refused = await reception.call_tool("read", {"type": "image"})
            assert refused.structured_content["error"]["code"] == "agent_scope"
        async with mcp(app, _agent_headers(dataset)) as steward:
            draft = await steward.call_tool("read", {"type": "draft"})
            plan = draft.structured_content["data"]["items"][0]
            assert {"plan", "items", "next", "writes"} <= set(plan)
            images = await steward.call_tool(
                "read", {"type": "image", "where": {"result": "ok"}}
            )
            said = json.dumps(images.structured_content["data"])
            assert "a.png" in said and "geometry" not in said

    run_scenario(tmp_path, monkeypatch, body)
