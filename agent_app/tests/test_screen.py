"""What the screens read: the gallery's badges per view and the overall map (step 6 design 5)."""

from agent_app.shapes import Create
from test_runs import DEFINITIONS, run_once, scenario

from agent_app import annotation_sets


def test_gallery_badges_and_map_follow_the_data(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        a, fail = ids["a.png"], ids["fail.png"]
        stages = (await client.get(f"/v1/datasets/{dataset}/progress")).json()["stages"]
        # Two stages (types design 17.1): the plan is made when it was run as it is
        # (definition 26.3), so a version never run is ① now.
        assert [s["state"] for s in stages] == ["now", "todo"]

        run = await run_once(client, app, dataset)
        page = (
            await client.get(
                f"/v1/datasets/{dataset}/gallery?view=run&run_id={run['id']}"
            )
        ).json()
        badges = {i["image"]["id"]: i["badge"] for i in page["items"]}
        assert badges[a]["kind"] == "detected"
        assert badges[fail]["kind"] == "failed"
        assert set(page["label_colors"]) == {"circle"}

        adoption = (
            await client.get(f"/v1/datasets/{dataset}/gallery?view=adoption")
        ).json()
        kinds = {i["image"]["id"]: i["badge"]["kind"] for i in adoption["items"]}
        assert kinds == {a: "result", fail: "none"}
        # ②: the adoption, and where none, what the newest run left (failed).
        production = (
            await client.get(f"/v1/datasets/{dataset}/gallery?view=production")
        ).json()
        kinds = {i["image"]["id"]: i["badge"]["kind"] for i in production["items"]}
        assert kinds == {a: "result", fail: "failed"}
        progress = (await client.get(f"/v1/datasets/{dataset}/progress")).json()
        assert [s["state"] for s in progress["stages"]] == ["done", "now"]
        assert progress["overall"] == {
            "kind": "missing",
            "stage": "production",
            "count": 1,
        }
        # Every image adopted or left out: complete, and no stage is "next" (found
        # 2026-10-05: a finished dataset still showed "now" on its last stage).
        await client.post(f"/v1/datasets/{dataset}/images/{fail}/exclude")
        progress = (await client.get(f"/v1/datasets/{dataset}/progress")).json()
        # Complete with nothing to fix: what is chosen is what training uses (user 2026-10-15).
        assert progress["overall"] == {"kind": "complete", "count": 1}
        assert "now" not in [s["state"] for s in progress["stages"]]

    scenario(tmp_path, monkeypatch, body)


def test_adoption_follows_the_marks(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        a, fail = ids["a.png"], ids["fail.png"]

        async def sources():
            page = (await client.get(f"/v1/datasets/{dataset}/adoption")).json()
            return {i["image_id"]: i["source"] for i in page["items"]}

        await run_once(client, app, dataset)
        assert await sources() == {a: "result", fail: "none"}
        await client.post(f"/v1/datasets/{dataset}/images/{a}/exclude")
        assert await sources() == {a: "excluded", fail: "none"}
        await client.post(f"/v1/datasets/{dataset}/images/{a}/include")
        assert (await sources())[a] == "result"

    scenario(tmp_path, monkeypatch, body)


def test_scan_lists_what_an_import_would_read(client, image_file, tmp_path):
    folder = tmp_path / "site"
    image_file((1, 2, 3), "a.png", folder)
    (folder / "notes.txt").write_text("x")
    scan = client.post("/v1/local-images/scan", json={"paths": [str(folder)]}).json()
    assert scan["count"] == 1 and scan["files"][0]["name"] == "a.png"
    thumb = client.get(f"/v1/images/{'img-' + '0' * 64}/thumbnail")
    assert thumb.status_code == 404


def test_objects_get_numbers_and_labels_keep_their_colors(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        db = app.state.db
        with db.transaction():
            set_id = annotation_sets.new_set(db, ids["a.png"])

        def box(x, y):
            return Create.model_validate(
                {
                    "op": "create",
                    "label": "circle",
                    "geometry": {"type": "bbox", "xywh": [x, y, 5, 5]},
                }
            )

        with db.transaction():
            annotation_sets.fill(
                db,
                set_id,
                [box(50, 60), box(10, 5), box(5, 70)],
                DEFINITIONS,
                [None, None, 9],
            )
        numbers = {
            tuple(x["geometry"]["xywh"][:2]): x["number"]
            for x in annotation_sets.current(db, set_id)
        }
        # Reading order (top first) for new ones; a kept number stays and is not given again.
        assert numbers == {(10, 5): 10, (50, 60): 11, (5, 70): 9}

        first = (await client.get(f"/v1/datasets/{dataset}/label-colors")).json()[
            "colors"
        ]
        await client.put(
            f"/v1/datasets/{dataset}/label-colors",
            json={"colors": {"circle": "#123456"}},
        )
        page = f"/v1/datasets/{dataset}/gallery?view=production"
        assert (await client.get(page)).json()["label_colors"] == {"circle": "#123456"}
        reset = (
            await client.post(f"/v1/datasets/{dataset}/label-colors/reset")
        ).json()["colors"]
        assert reset == first

    scenario(tmp_path, monkeypatch, body)


def test_the_eye_lists_the_labels_of_the_plan_looked_at(tmp_path, monkeypatch):
    # Definition 37.3 (user 2026-10-23): the eye listed every label the dataset's plans ever
    # had, not those of the plan the screen is judged by. A label keeps its color in each.
    async def body(app, client, dataset, ids):
        base = f"/v1/datasets/{dataset}"
        dot = [{"name": "dot", "shape": "bbox", "attributes": []}]
        await client.put(
            f"{base}/drafts/instruction",
            json={"text": "draft", "label_definitions": dot},
        )
        write = (await client.get(f"{base}/plan/state")).json()["write_id"]

        async def colors(query):
            return (await client.get(f"{base}/label-colors{query}")).json()["colors"]

        every = await colors("")
        assert {"circle", "dot"} <= set(every)
        assert await colors("?revision=1") == {"circle": every["circle"]}
        assert await colors(f"?write={write}") == {"dot": every["dot"]}

    scenario(tmp_path, monkeypatch, body)


def test_the_built_screens_top_files_are_served_and_nothing_outside(
    tmp_path, monkeypatch
):
    # 2026-10-30: the page's mark (/icon.png, copied from ui/public) came back as the page itself,
    # so the app's window showed the browser's mark in the taskbar.
    from fastapi.testclient import TestClient

    from agent_app import app as app_module

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>page</html>", encoding="utf-8")
    (dist / "icon.png").write_bytes(b"\x89PNG mark")
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")
    monkeypatch.setattr(app_module, "UI_DIST", dist)
    with TestClient(
        app_module.create_app(tmp_path / "screen.db"), base_url="http://127.0.0.1"
    ) as client:
        assert client.get("/icon.png").content == b"\x89PNG mark"
        assert client.get("/..%2Fsecret.txt").text == "<html>page</html>"
        assert client.get("/d/some/route").text == "<html>page</html>"
