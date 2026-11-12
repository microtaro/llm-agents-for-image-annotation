"""Writing datasets out (definition 60.4): this app's form and COCO's, nothing in the app
changing and no folder written over."""

import io
import json
from pathlib import Path

import httpx
from agent_app.app import create_app
from agent_app.dataset_export import _file_names
from test_runs import DEFINITIONS, run_once, save_version, scenario


def test_a_dataset_is_written_out_whole_or_as_coco_never_over_another(
    tmp_path, monkeypatch
):
    # 2026-10-28: datasets written out to give to another person using the app, and as COCO's
    # JSON to open and analyse in other tools (COCO Annotator and the like).
    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset)
        out = tmp_path / "out"
        out.mkdir()
        asked = {"dataset_ids": [dataset], "dest": str(out)}
        whole = await client.post("/v1/library/export", json={**asked, "format": "app"})
        assert whole.status_code == 200, whole.text
        folder = Path(whole.json()["written"][0]["path"])
        document = json.loads((folder / "dataset.json").read_text(encoding="utf-8"))
        assert (document["format"], document["version"]) == ("agent-app-dataset", 6)
        # dataset.json what other software reads (README.md says it); app.json this app's own.
        # 2026-11-10: one README per language (both in one file, one side came first garbled or
        # unreadable), each with the form's version written.
        english = (folder / "README.md").read_text(encoding="utf-8")
        japanese = (folder / "README.ja.md").read_text(encoding="utf-8")
        assert english.isascii() and "データセット" in japanese
        assert "version 6)" in english and "形の版 6）" in japanese
        assert [label["name"] for label in document["labels"]] == ["circle"]
        assert {i["name"] for i in document["images"]} == {"a.png", "fail.png"}
        assert all((folder / i["file"]).is_file() for i in document["images"])
        (found,) = [i["annotation"] for i in document["images"] if i["name"] == "a.png"]
        assert found["by"] == "ai" and found["objects"][0]["label"] == "circle"
        assert found["objects"][0]["geometry"]["type"] == "bbox"
        assert "app" not in document
        history = json.loads((folder / "app.json").read_text(encoding="utf-8"))
        assert (history["format"], history["version"]) == ("agent-app-dataset", 6)
        app_part = history["app"]
        assert app_part["instructions"] and app_part["runs"] and app_part["annotations"]
        assert isinstance(app_part["instructions"][0]["payload_json"], dict)
        coco = await client.post("/v1/library/export", json={**asked, "format": "coco"})
        second = Path(coco.json()["written"][0]["path"])
        # The first one's folder is there: a new one beside it.
        assert second.name == f"{folder.name} (2)"
        written = json.loads((second / "annotations.json").read_text(encoding="utf-8"))
        assert [c["name"] for c in written["categories"]] == ["circle"]
        (annotation,) = written["annotations"]
        assert annotation["attributes"] == {"color": "red"}
        assert len(annotation["bbox"]) == 4
        # Only the images training uses: one with no annotation yet is not a negative (2026-10-30
        # review: left out, or not annotated yet, it was an image of no object).
        assert [i["file_name"] for i in written["images"]] == ["a.png"]
        assert sorted(p.name for p in (second / "images").iterdir()) == ["a.png"]
        assert not [p for p in out.iterdir() if p.name.startswith(".")]
        # Each image's annotation now by the latest version saved, as the library's card counts
        # it: a draft of other labels being written changes nothing written out (user
        # 2026-10-28: by the gallery, a draft's new label left every annotation out).
        latest = (
            await client.get(f"/v1/datasets/{dataset}/instructions/latest")
        ).json()
        draft = {
            "text": "四角も",
            "label_definitions": [
                *latest["label_definitions"],
                {"name": "square", "shape": "bbox"},
            ],
        }
        await client.put(f"/v1/datasets/{dataset}/drafts/instruction", json=draft)
        again = await client.post("/v1/library/export", json={**asked, "format": "app"})
        document = json.loads(
            (Path(again.json()["written"][0]["path"]) / "dataset.json").read_text(
                encoding="utf-8"
            )
        )
        assert [label["name"] for label in document["labels"]] == ["circle"]
        assert [
            (i["name"], len((i["annotation"] or {}).get("objects", [])))
            for i in document["images"]
        ] == [("a.png", 1), ("fail.png", 0)]

    scenario(tmp_path, monkeypatch, body)


def test_a_worker_writes_out_what_its_place_lets_it():
    # 2026-10-28 (definition 60.6): writing out changes no data, so no proposal; the library's
    # worker writes any datasets out, a dataset's worker its own only.
    from agent_app.authority import Allowed, Caller, permit

    asked = {"dataset_ids": ["a", "b"], "dest": "/exports"}
    library = Caller("agent", "reception", None, 1)
    steward = Caller("agent", "steward", "a", 2)
    assert isinstance(permit(library, "datasets_export", asked), Allowed)
    assert not isinstance(permit(steward, "datasets_export", asked), Allowed)
    own = {**asked, "dataset_ids": ["a"]}
    assert isinstance(permit(steward, "datasets_export", own), Allowed)


def test_the_workers_tools_name_folders_of_this_computer_in_its_form():
    # 2026-11-02: asked to write out, the steward told a person on Windows to give a folder
    # "on the server", e.g. "/home/…/export": the tools said "server" and gave no example in
    # this computer's form.
    from agent_app.mcp_general import GENERAL
    from agent_app.system import FOLDER_EXAMPLE

    for name, tool in GENERAL.items():
        fields = [f.description or "" for f in tool.input.model_fields.values()]
        for text in (tool.description, *fields):
            if "folder" in text.lower() or "path" in text.lower():
                assert "server" not in text.lower(), (name, text)
    export = GENERAL["datasets_export"]
    assert FOLDER_EXAMPLE in export.description
    assert FOLDER_EXAMPLE in export.input.model_fields["dest"].description


def test_a_dataset_written_out_is_taken_in_again_as_it_was(tmp_path, monkeypatch):
    # 2026-10-28 (definition 60.3): what this app wrote out is taken in by another person as a
    # new dataset with its plan, records and annotations; the scan tells what the folder holds.
    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset)
        out = tmp_path / "out"
        out.mkdir()
        asked = {"dataset_ids": [dataset], "dest": str(out), "format": "app"}
        folder = (await client.post("/v1/library/export", json=asked)).json()[
            "written"
        ][0]
        # The annotations now, as the cards count them, apart from every record's (2026-10-29:
        # the count read the wrong place and said 0).
        assert (folder["annotations"], folder["annotations_in_records"]) == (1, 1)
        scanned = (
            await client.post("/v1/local-images/scan", json={"paths": [str(out)]})
        ).json()
        assert scanned["written"]["kind"] == "app"
        assert [d["name"] for d in scanned["written"]["datasets"]] == [folder["name"]]
        taken = await client.post("/v1/library/import", json={"path": str(out)})
        assert taken.status_code == 200, taken.text
        (made,) = taken.json()["datasets"]
        assert made["name"] == f"{folder['name']} (2)"
        before = (await client.get(f"/v1/datasets/{dataset}/gallery?view=run")).json()
        after = (await client.get(f"/v1/datasets/{made['id']}/gallery?view=run")).json()
        # The same images in the same states, each with its annotation as it was.
        assert [
            (i["image"]["id"], i["badge"]["kind"], len(i["annotations"]))
            for i in after["items"]
        ] == [
            (i["image"]["id"], i["badge"]["kind"], len(i["annotations"]))
            for i in before["items"]
        ]
        versions = app.state.db.one(
            "SELECT count(*) AS n FROM instructions WHERE dataset_id=?", (made["id"],)
        )
        assert versions["n"] == 1

    scenario(tmp_path, monkeypatch, body)


def _rle_string(counts):
    """COCO's compressed run-length string (pycocotools' rleToString), to write one here."""
    out = []
    for i, x in enumerate(counts):
        if i > 2:
            x -= counts[i - 2]
        more = True
        while more:
            c = x & 0x1F
            x >>= 5
            more = x != -1 if c & 0x10 else x != 0
            if more:
                c |= 0x20
            out.append(chr(c + 48))
    return "".join(out)


def test_an_object_names_its_parent_by_an_id_one_only_in_its_image(
    tmp_path, monkeypatch
):
    # 2026-10-29: numbers are per label ("box 2"), so a parent named by its number could be
    # several objects of the image; each object has an id in its image, the parent by it.
    async def body(app, client, dataset, ids):
        save_version(
            app.state.db,
            dataset,
            {
                "text": "円と点",
                "label_definitions": [
                    *DEFINITIONS,
                    {"name": "dot", "shape": "bbox", "parent": "circle"},
                ],
            },
        )
        first = await run_once(client, app, dataset)
        a = ids["a.png"]
        results = (await client.get(f"/v1/runs/{first['id']}/results")).json()
        made = next(r["result_id"] for r in results["results"] if r["image_id"] == a)

        def box(label, xywh, **more):
            return {"label": label, "geometry": {"type": "bbox", "xywh": xywh}, **more}

        fixed = await client.post(
            f"/v1/datasets/{dataset}/images/{a}/fixes",
            json={
                "from_result_id": made,
                "annotations": [
                    box("circle", [10, 10, 60, 60], ref="one"),
                    box("dot", [20, 20, 5, 5], parent="one"),
                    box("circle", [120, 10, 60, 60], ref="two"),
                    box("dot", [130, 20, 5, 5], parent="two"),
                ],
            },
        )
        assert fixed.status_code == 201, fixed.text
        out = tmp_path / "out"
        out.mkdir()
        written = await client.post(
            "/v1/library/export",
            json={"dataset_ids": [dataset], "dest": str(out), "format": "app"},
        )
        folder = Path(written.json()["written"][0]["path"])
        document = json.loads((folder / "dataset.json").read_text(encoding="utf-8"))
        (found,) = [i["annotation"] for i in document["images"] if i["name"] == "a.png"]
        objects = {o["id"]: o for o in found["objects"]}
        assert len(objects) == 4

        def at(o):
            return (o["label"], o["geometry"]["xywh"][0])

        parents = {
            at(o): at(objects[o["parent"]])
            for o in objects.values()
            if o["parent"] is not None
        }
        assert parents == {("dot", 20): ("circle", 10), ("dot", 130): ("circle", 120)}

    scenario(tmp_path, monkeypatch, body)


def test_coco_is_taken_in_as_a_first_version_and_a_record_taken_in(
    tmp_path, monkeypatch
):
    # 2026-10-28 (definition 60.11, A): COCO's JSON as other tools write it (FiftyOne: data/ and
    # labels.json) becomes a dataset whose first version is made from its categories, and one
    # record taken in that makes each image's annotation now; this app's own COCO comes back.
    from PIL import Image

    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset)
        out = tmp_path / "out"
        out.mkdir()
        asked = {"dataset_ids": [dataset], "dest": str(out), "format": "coco"}
        folder = (await client.post("/v1/library/export", json=asked)).json()[
            "written"
        ][0]
        taken = await client.post(
            "/v1/library/import",
            json={"path": folder["path"], "name": "戻した", "purpose": "確かめ"},
        )
        assert taken.status_code == 200, taken.text
        made = taken.json()["datasets"][0]
        gallery = (
            await client.get(f"/v1/datasets/{made['id']}/gallery?view=run")
        ).json()
        by_name = {i["image"]["name"]: i for i in gallery["items"]}
        assert by_name["a.png"]["badge"]["by"] == "import"
        assert len(by_name["a.png"]["annotations"]) == 1
        # The image with no annotation was not written out.
        assert list(by_name) == ["a.png"] and made["unannotated"] == 0
        records = (await client.get(f"/v1/datasets/{made['id']}/objects/run")).json()[
            "items"
        ]
        assert [(r["kind"], r["number"]) for r in records] == [("import", 1)]
        # Another tool's: masks and outlines, compressed or not.
        other = tmp_path / "fiftyone"
        (other / "data").mkdir(parents=True)
        Image.new("RGB", (20, 10), (9, 9, 9)).save(other / "data" / "x.png")
        square = [2, 2, 8, 2, 8, 8, 2, 8]
        counts = [
            12,
            4,
            6,
            4,
            174,
        ]  # off 12, on 4, off 6, on 4, off the rest (column order)
        objects = [
            {"bbox": [1, 1, 5, 5], "segmentation": []},
            {"bbox": [2, 2, 6, 6], "segmentation": [square]},
            {
                "bbox": [2, 2, 16, 6],
                "segmentation": [square, [12, 2, 18, 2, 18, 8, 12, 8]],
            },
            {
                "bbox": [1, 2, 2, 4],
                "segmentation": {"size": [10, 20], "counts": counts},
            },
            {
                "bbox": [1, 2, 2, 4],
                "segmentation": {"size": [10, 20], "counts": _rle_string(counts)},
            },
        ]
        (other / "labels.json").write_text(
            json.dumps(
                {
                    "images": [
                        {"id": 7, "file_name": "x.png", "width": 20, "height": 10}
                    ],
                    "categories": [{"id": 3, "name": "part"}],
                    "annotations": [
                        {
                            "id": n,
                            "image_id": 7,
                            "category_id": 3,
                            "attributes": {"side": "left"},
                            **o,
                        }
                        for n, o in enumerate(objects, start=1)
                    ],
                }
            )
        )
        scanned = (
            await client.post("/v1/local-images/scan", json={"paths": [str(other)]})
        ).json()
        assert scanned["written"]["kind"] == "coco"
        taken = await client.post(
            "/v1/library/import",
            json={"path": str(other), "name": "ほか", "purpose": "形"},
        )
        assert taken.status_code == 200, taken.text
        made = taken.json()["datasets"][0]
        assert made["skipped"] == {"images": 0, "objects": 0}
        (item,) = (
            await client.get(f"/v1/datasets/{made['id']}/gallery?view=run")
        ).json()["items"]
        kinds = sorted(a["geometry"]["type"] for a in item["annotations"])
        # The box only of a label with outlines is one outline (2026-10-30: kept as a box, it
        # broke the label's shape).
        assert kinds == ["mask", "mask", "mask", "polygon", "polygon"]
        plan = app.state.db.one(
            "SELECT payload_json FROM instructions WHERE dataset_id=?", (made["id"],)
        )
        (label,) = json.loads(plan["payload_json"])["label_definitions"]
        assert (label["name"], label["shape"]) == ("part", "polygon")
        assert [a["name"] for a in label["attributes"]] == ["side"]

    scenario(tmp_path, monkeypatch, body)


def test_a_folder_of_two_datasets_is_taken_in_by_one_decision(tmp_path, monkeypatch):
    # Reviews 2026-10-28 (A#1, B#9): each dataset of the folder recorded the decision again;
    # the second failed, and the first stayed in the library.
    async def body(app, client, dataset, ids):
        other = (
            await client.post(
                "/v1/datasets",
                json={"name": "二つ目", "purpose": "円", "image_ids": [ids["a.png"]]},
            )
        ).json()["id"]
        out = tmp_path / "two"
        out.mkdir()
        asked = {"dataset_ids": [dataset, other], "dest": str(out), "format": "app"}
        assert (await client.post("/v1/library/export", json=asked)).status_code == 200
        taken = await client.post(
            "/v1/library/import",
            json={"path": str(out)},
            headers={"X-Annotation-Decision": "dec-two"},
        )
        assert taken.status_code == 200, taken.text
        made = [d["id"] for d in taken.json()["datasets"]]
        assert len(made) == 2
        decision = app.state.db.one(
            "SELECT outcome_json FROM decisions WHERE id='dec-two'"
        )
        assert [d["id"] for d in json.loads(decision[0])["datasets"]] == made

    scenario(tmp_path, monkeypatch, body)


def test_a_record_of_an_image_taken_out_is_taken_in_elsewhere(tmp_path, monkeypatch):
    # Review 2026-10-28 (B#5): the records were written out whole, the images only those the
    # dataset held, so a library without the image taken out could not take the folder in.
    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset)
        removed = await client.post(
            f"/v1/datasets/{dataset}/images/remove",
            json={"image_ids": [ids["fail.png"]]},
        )
        assert removed.status_code == 200, removed.text
        out = tmp_path / "out"
        out.mkdir()
        asked = {"dataset_ids": [dataset], "dest": str(out), "format": "app"}
        assert (await client.post("/v1/library/export", json=asked)).status_code == 200
        elsewhere = create_app(tmp_path / "elsewhere.db")
        async with (
            elsewhere.router.lifespan_context(elsewhere),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=elsewhere),
                base_url="http://127.0.0.1",
            ) as there,
        ):
            taken = await there.post("/v1/library/import", json={"path": str(out)})
            assert taken.status_code == 200, taken.text
            (made,) = taken.json()["datasets"]
            assert made["images"] == 1

    scenario(tmp_path, monkeypatch, body)


def test_each_image_has_a_file_of_its_own():
    # Review 2026-10-28 (B#2): a name met again took the image's place, which could be another
    # image's own name; one file was written over the other.
    names = _file_names(
        [
            {"id": "1", "name": "a.png"},
            {"id": "2", "name": "a.png"},
            {"id": "3", "name": "a-2.png"},
            {"id": "4", "name": "a.png"},
        ]
    )
    assert len(set(names.values())) == 4
    assert names["1"] == "a.png"


def test_coco_reads_no_file_outside_its_folder_and_no_run_past_the_image(tmp_path):
    # Review 2026-10-28 (B#8): a file_name of an absolute path or with ".." read an image from
    # outside the folder; (B#7) a run of a mask's RLE was made whole before it was cut to the
    # image, so a huge count took the memory.
    from agent_app.coco_import import _image_file, _mask_png
    from PIL import Image

    folder = tmp_path / "coco"
    (folder / "images").mkdir(parents=True)
    Image.new("RGB", (4, 2)).save(folder / "images" / "in.png")
    Image.new("RGB", (4, 2)).save(tmp_path / "outside.png")
    assert _image_file(folder, str(tmp_path / "outside.png")) is None
    assert _image_file(folder, "../outside.png") is None
    assert _image_file(folder, "images/../../outside.png") is None
    # A path written elsewhere, of an image the folder has by its name: that one.
    assert _image_file(folder, "/somewhere/else/in.png") == folder / "images" / "in.png"
    whole = _mask_png(4, 2, {"size": [2, 4], "counts": [0, 10**12]})
    assert Image.open(io.BytesIO(whole)).getbbox() == (0, 0, 4, 2)


def test_a_plan_draft_is_taken_in_as_a_draft_written(tmp_path, monkeypatch):
    # 2026-10-30 (the zip given to people): a dataset with a plan's draft taken in had a draft
    # pointing at no write, and its progress was a 500.
    async def body(app, client, dataset, ids):
        await run_once(client, app, dataset)
        draft = {
            "text": "円を全部囲む",
            "label_definitions": DEFINITIONS,
            "leave_out": [],
        }
        written = await client.put(
            f"/v1/datasets/{dataset}/drafts/instruction", json=draft
        )
        assert written.status_code == 200, written.text
        out = tmp_path / "out"
        out.mkdir()
        asked = {"dataset_ids": [dataset], "dest": str(out), "format": "app"}
        assert (await client.post("/v1/library/export", json=asked)).status_code == 200
        taken = await client.post("/v1/library/import", json={"path": str(out)})
        (made,) = taken.json()["datasets"]
        progress = await client.get(f"/v1/datasets/{made['id']}/progress")
        assert progress.status_code == 200, progress.text
        there = (
            await client.get(f"/v1/datasets/{made['id']}/drafts/instruction")
        ).json()
        assert there["text"] == "円を全部囲む"

    scenario(tmp_path, monkeypatch, body)
