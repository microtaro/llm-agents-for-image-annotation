"""What an AI is told of an image and in which pixels it answers (definition 29)."""

import json
from uuid import uuid4

from test_drafts_and_ai import mcp
from test_runs import as_worker, scenario

BOX = {"type": "bbox", "xywh": [10, 5, 20, 15]}


def test_an_ai_answers_in_the_pixels_of_an_image_it_saw(tmp_path, monkeypatch):
    # User 2026-10-21: no scale or crop is told and none is returned; coordinates are those of
    # the image seen, and the server keeps the rest.
    async def body(app, client, dataset, ids):
        image = ids["a.png"]
        result_id, worker = await as_worker(client, app, dataset, image)
        async with mcp(app, worker) as ai:
            shown = await ai.call_tool(
                "observe",
                {"target": {"image_id": image}, "view": {"max_side": 120}},
            )
            view = shown.structured_content["view"]
            assert set(view) == {
                "view_id",
                "image_id",
                "output_size",
                "shrunk",
                "drawn",
            }
            assert view["output_size"] == [120, 60] and view["shrunk"]
            create = {"op": "create", "label": "circle", "geometry": BOX}
            batch = {
                "request_id": str(uuid4()),
                "base_revision": 1,
                "operations": [create],
            }
            args = {"result_id": result_id, "batch": batch}
            refused = await ai.call_tool("save_and_observe", args)
            assert refused.structured_content["error"]["code"] == "invalid_input"
            written = await ai.call_tool(
                "save_and_observe",
                {**args, "batch": {**batch, "coordinate_view_id": view["view_id"]}},
            )
            out = written.structured_content
        assert out["ok"] and "geometry" not in json.dumps(out["data"])
        # Drawn back on the whole image (240 x 120, as it is): its own pixels.
        assert [20, 10, 40, 30] in [d["geometry"]["xywh"] for d in out["view"]["drawn"]]
        stored = (await client.get(f"/v1/results/{result_id}")).json()
        assert [20, 10, 40, 30] in [
            a["geometry"]["xywh"] for a in stored["annotations"]
        ]

    scenario(tmp_path, monkeypatch, body)


def test_a_crop_comes_with_a_margin_and_enlarged(tmp_path, monkeypatch):
    # User 2026-10-21: a crop came back at its original pixels only (a small one stayed small);
    # it gets a margin (20 px of the original, the AI's own in its pixels) and is enlarged up to
    # 8x to the view size, and an outline on it is kept in original pixels. What was written
    # on a crop is seen whole too before going on (definition 32.1, 7).
    async def body(app, client, dataset, ids):
        image = ids["a.png"]
        result_id, worker = await as_worker(client, app, dataset, image)
        async with mcp(app, worker) as ai:
            whole = await ai.call_tool(
                "observe", {"target": {"image_id": image}, "view": {"max_side": 120}}
            )
            first = whole.structured_content["view"]["view_id"]
            # [50, 25, 20, 15] on the half-size image is [100, 50, 40, 30] of the original.
            crop = {"crop_xywh": [50, 25, 20, 15], "coordinate_view_id": first}
            near = await ai.call_tool(
                "observe", {"target": {"image_id": image}, "view": crop}
            )
            wide = await ai.call_tool(
                "observe",
                {"target": {"image_id": image}, "view": {**crop, "margin": 5}},
            )
            zoomed = near.structured_content["view"]
            create = {
                "op": "create",
                "label": "circle",
                "geometry": {"type": "bbox", "xywh": [160, 160, 320, 240]},
            }
            written = await ai.call_tool(
                "save_and_observe",
                {
                    "result_id": result_id,
                    "batch": {
                        "request_id": str(uuid4()),
                        "base_revision": 1,
                        "coordinate_view_id": zoomed["view_id"],
                        "operations": [create],
                    },
                    "view": crop,
                },
            )
        frames = {
            v["view_id"]: json.loads(
                app.state.db.one(
                    "SELECT frame_json FROM views WHERE id=?", (v["view_id"],)
                )[0]
            )
            for v in (zoomed, wide.structured_content["view"])
        }
        near_frame, wide_frame = frames.values()
        assert near_frame["crop_xywh"] == [80, 30, 80, 70]
        assert zoomed["output_size"] == [640, 560]  # 8x, under the view size
        assert wide_frame["crop_xywh"] == [90, 40, 60, 50]  # 5 px there is 10 here
        out = written.structured_content
        assert out["ok"], out["error"]
        assert out["whole"]["output_size"] == [240, 120]
        assert len(written.content) == 3  # the text, the crop and the whole image
        stored = (await client.get(f"/v1/results/{result_id}")).json()
        assert [100, 50, 40, 30] in [
            a["geometry"]["xywh"] for a in stored["annotations"]
        ]

    scenario(tmp_path, monkeypatch, body)


def test_an_update_of_the_shape_alone_keeps_the_values(tmp_path, monkeypatch):
    # Review 2026-10-28 (C#2): an AI that moved a box, naming its label and shape only, erased
    # its values and its parent: the fields it left out were sent as null, and null clears.
    async def body(app, client, dataset, ids):
        image = ids["a.png"]
        result_id, worker = await as_worker(client, app, dataset, image)
        async with mcp(app, worker) as ai:
            shown = await ai.call_tool(
                "observe", {"target": {"image_id": image}, "view": {"max_side": 120}}
            )
            view_id = shown.structured_content["view"]["view_id"]

            async def write(revision, operation):
                written = await ai.call_tool(
                    "save_and_observe",
                    {
                        "result_id": result_id,
                        "batch": {
                            "request_id": str(uuid4()),
                            "base_revision": revision,
                            "coordinate_view_id": view_id,
                            "operations": [operation],
                        },
                    },
                )
                out = written.structured_content
                assert out["ok"], out["error"]
                return out["data"]

            made = await write(
                1,
                {
                    "op": "create",
                    "label": "circle",
                    "geometry": BOX,
                    "attributes": {"color": "red"},
                },
            )
            await write(
                made["revision"],
                {
                    "op": "update",
                    "id": made["created_ids"][0],
                    "label": "circle",
                    "geometry": {"type": "bbox", "xywh": [12, 5, 20, 15]},
                },
            )
        stored = (await client.get(f"/v1/results/{result_id}")).json()["annotations"]
        moved = next(a for a in stored if a["geometry"]["xywh"] == [24, 10, 40, 30])
        assert moved["attributes"] == {"color": "red"}

    scenario(tmp_path, monkeypatch, body)
