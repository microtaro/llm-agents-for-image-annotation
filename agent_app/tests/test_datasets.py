from agent_app.actors import OUTSIDE
from test_runs import save_version


def test_purpose_is_fixed_and_images_keep_where_they_came_from(client, image_file):
    first = image_file((10, 20, 30), "a.png")
    imported = client.post(
        "/v1/images/import", json={"paths": [str(first), str(first)]}
    ).json()
    assert len({i["id"] for i in imported["images"]}) == 1
    image_id = imported["images"][0]["id"]
    copy = image_file((10, 20, 30), "copy.png")
    again = client.post("/v1/images/import", json={"paths": [str(copy)]}).json()[
        "images"
    ][0]
    assert again["id"] == image_id and len(again["source_paths"]) == 2

    dataset = client.post(
        "/v1/datasets", json={"name": "boxes", "purpose": "read LOT"}
    ).json()
    refused = client.patch(f"/v1/datasets/{dataset['id']}", json={"purpose": "other"})
    assert (
        refused.status_code == 422
        and refused.json()["error"]["code"] == "purpose_immutable"
    )
    renamed = client.patch(
        f"/v1/datasets/{dataset['id']}", json={"name": "boxes 2"}
    ).json()
    assert renamed["name"] == "boxes 2" and renamed["purpose"] == "read LOT"

    added = client.post(
        f"/v1/datasets/{dataset['id']}/images",
        json={"image_ids": [image_id], "source_path": "/site/A"},
    ).json()
    assert added == {"added": [image_id], "already": []}
    held = client.get(f"/v1/datasets/{dataset['id']}").json()["images"][0]
    assert (
        held["source_path"] == "/site/A"
        and held["added_at"]
        and held["excluded"] is False
    )


def test_instruction_versions_tell_when_the_requirement_changed(client):
    dataset = client.post("/v1/datasets", json={"name": "d", "purpose": "p"}).json()
    url = f"/v1/datasets/{dataset['id']}/instructions"
    db = client.app.state.db

    def saved(plan):
        return save_version(db, dataset["id"], plan, OUTSIDE)

    one = {"text": "t", "label_definitions": [{"name": "box", "shape": "bbox"}]}
    # No route saves a version by itself (user 2026-10-28, review A#4): a run decided does.
    assert client.post(url, json=one).status_code == 405
    assert saved(one)["requirement_changed"] is True
    reworded = {
        **one,
        "text": "other words",
        "label_definitions": [{"name": "box", "shape": "bbox", "description": "x"}],
    }
    second = saved(reworded)
    assert second["revision"] == 2 and second["requirement_changed"] is False
    more = {
        **one,
        "label_definitions": [
            {"name": "box", "shape": "bbox"},
            {"name": "lid", "shape": "bbox"},
        ],
    }
    assert saved(more)["requirement_changed"] is True
    latest = client.get(f"{url}/latest").json()
    assert latest["revision"] == 3 and len(latest["label_definitions"]) == 2
    # Who made each, in one word (definition 21.2): with no worker's mark, the outside.
    assert [v["created_by"] for v in client.get(url).json()["instructions"]] == [
        "outside"
    ] * 3


def test_images_imported_into_a_dataset_keep_their_files(client, image_file, tmp_path):
    # Found 2026-10-05: a dataset made from imported images forgot where each came from.
    folder = tmp_path / "site-a"
    first = image_file((1, 2, 3), "a.png", folder)
    image_file((4, 5, 6), "b.png", folder)
    made = client.post(
        "/v1/datasets",
        json={"name": "現場A", "purpose": "箱を数える", "paths": [str(folder)]},
    ).json()
    assert [i["source_path"] for i in made["images"]] == [
        str(first.resolve()),
        str((folder / "b.png").resolve()),
    ]
    other = image_file((7, 8, 9), "c.png", tmp_path / "site-b")
    added = client.post(
        f"/v1/datasets/{made['id']}/images/import", json={"paths": [str(other)]}
    ).json()
    assert len(added["added"]) == 1
    sources = client.get(f"/v1/datasets/{made['id']}").json()["sources"]
    assert sources == [
        {"folder": str(folder.resolve()), "count": 2},
        {"folder": str((tmp_path / "site-b").resolve()), "count": 1},
    ]


def test_copy_brings_the_plan_as_a_draft_and_delete_keeps_images(client, image_file):
    image = client.post(
        "/v1/images/import", json={"paths": [str(image_file())]}
    ).json()["images"][0]
    made = client.post(
        "/v1/datasets", json={"name": "A", "purpose": "box", "image_ids": [image["id"]]}
    ).json()
    save_version(
        client.app.state.db,
        made["id"],
        {"label_definitions": [{"name": "box", "shape": "bbox"}]},
    )
    copy = client.post(
        f"/v1/datasets/{made['id']}/copy", json={"name": "B", "purpose": "other"}
    ).json()
    # The plan comes as a draft started from A's version (definition 15.1): a version is made
    # only when a run is decided.
    assert copy["image_count"] == 1 and copy["latest_revision"] is None
    draft = f"/v1/datasets/{copy['id']}/drafts/instruction"
    assert client.get(draft).json()["from"] == {
        "kind": "version",
        "dataset_id": made["id"],
        "revision": 1,
    }
    # Before a version, nothing is used of the images there are (not "0/0").
    training = client.get(f"/v1/datasets/{copy['id']}/training").json()
    assert (training["used"], training["images"]) == (0, 1)
    # Where it came from stays (issue #4 F-19, definition 21.5).
    db = client.app.state.db
    assert db.one(
        "SELECT from_dataset_id, kind FROM dataset_sources WHERE dataset_id=?",
        (copy["id"],),
    )[:] == (made["id"], "copy")

    assert client.delete(f"/v1/datasets/{made['id']}").status_code == 200
    assert client.get(f"/v1/datasets/{made['id']}").status_code == 404
    assert client.get(f"/v1/images/{image['id']}").status_code == 200
    assert client.get(draft).json()["label_definitions"][0]["name"] == "box"


def test_nothing_importable_makes_no_dataset_and_a_folder_twice_counts_once(
    client, image_file
):
    first = image_file((10, 20, 30), "a.png")
    folder = str(first.parent)
    scanned = client.post(
        "/v1/local-images/scan", json={"paths": [folder, folder]}
    ).json()
    assert scanned["count"] == len({f["path"] for f in scanned["files"]})
    # A file named as an image that is not one: every file is refused.
    broken = first.parent / "broken.png"
    broken.write_bytes(b"not an image")
    before = len(client.get("/v1/datasets").json()["datasets"])
    refused = client.post(
        "/v1/datasets",
        json={"name": "x", "purpose": "y", "paths": [str(broken)]},
    )
    error = refused.json()["error"]
    assert refused.status_code == 422 and error["code"] == "nothing_imported"
    assert error["details"]["reasons"] == {"invalid_image": 1}
    assert len(client.get("/v1/datasets").json()["datasets"]) == before


def test_an_image_taken_out_comes_back(client, image_file):
    a = image_file((10, 20, 30), "a.png")
    b = image_file((40, 20, 30), "b.png")
    dataset = client.post(
        "/v1/datasets",
        json={"name": "x", "purpose": "y", "paths": [str(a), str(b)]},
    ).json()
    first = dataset["images"][0]["image_id"]
    removed = client.post(
        f"/v1/datasets/{dataset['id']}/images/remove", json={"image_ids": [first]}
    ).json()
    assert removed == {"removed": [first]}
    # Who took it out and when stays (issue #4 F-19).
    found = client.app.state.db.one(
        "SELECT removed_by FROM dataset_image_removals WHERE image_id=?", (first,)
    )
    assert found["removed_by"] == "outside"
    held = client.get(f"/v1/datasets/{dataset['id']}").json()
    assert held["image_count"] == 1
    client.post(f"/v1/datasets/{dataset['id']}/images", json={"image_ids": [first]})
    assert client.get(f"/v1/datasets/{dataset['id']}").json()["image_count"] == 2


def test_a_folder_is_chosen_in_the_windows_window(client, image_file, monkeypatch):
    # User 2026-10-23: typing a folder's path to make a dataset was a chore; the Windows window
    # of annotation_server was not carried over (definition 43).
    import json
    from types import SimpleNamespace

    from agent_app import native_picker

    folder = image_file((1, 2, 3), "a.png").parent / "動物"
    first = image_file((1, 2, 3), "A001.png", folder)
    second = image_file((4, 5, 6), "A002.png", folder)
    chosen = [str(folder / "（このフォルダの画像すべて）")]
    monkeypatch.setattr(native_picker, "powershell", lambda: "pwsh")
    monkeypatch.setattr(native_picker, "windows_path", str)
    monkeypatch.setattr(native_picker, "server_path", str)
    monkeypatch.setattr(
        native_picker.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(stdout=json.dumps({"paths": chosen})),
    )
    body = {"directory": None, "title": "t", "whole_folder": "w"}
    whole = client.post("/v1/local-images/select", json=body).json()
    assert whole == {"directory": str(folder), "left_out": [], "cancelled": False}
    chosen[:] = [str(second)]
    some = client.post("/v1/local-images/select", json=body).json()
    assert some["left_out"] == [str(first)]
    chosen.clear()
    assert client.post("/v1/local-images/select", json=body).json()["cancelled"]


def test_a_dataset_is_called_by_a_number_never_given_again(client):
    # 2026-10-28 (definition 61): a long name was hard to call; a number in the order made, the
    # same after other datasets go, and never given again (a deleted one's neither, so "#2" in
    # an earlier talk keeps meaning the one deleted).
    made = [
        client.post("/v1/datasets", json={"name": n, "purpose": "p"}).json()
        for n in ("a", "b")
    ]
    assert [d["number"] for d in made] == [1, 2]
    assert client.delete(f"/v1/datasets/{made[1]['id']}").status_code == 200
    third = client.post("/v1/datasets", json={"name": "c", "purpose": "p"}).json()
    assert third["number"] == 3
    listed = client.get("/v1/datasets").json()["datasets"]
    assert sorted(d["number"] for d in listed) == [1, 3]


def test_the_settings_say_how_big_the_data_kept_is(client, image_file):
    # 2026-10-28: the app keeps its own copy of every image, so it grows; the settings say the
    # database's size and the images' on disk, and the room left.
    path = image_file((10, 20, 30), "a.png")
    client.post("/v1/images/import", json={"paths": [str(path)]})
    found = client.get("/v1/storage").json()
    assert found["database"]["bytes"] > 0
    assert found["files"]["images"] == {"count": 1, "bytes": path.stat().st_size}
    assert found["files"]["masks"]["count"] == 0
    assert 0 < found["disk"]["free"] <= found["disk"]["total"]


def test_a_clone_starts_with_its_samples_once(tmp_path, monkeypatch):
    """The app's own database made by this start takes in the samples beside it; not one made
    before, nor another database (user 2026-11-11: a clone starts with the samples, as the zip)."""
    from agent_app.db import Database

    from agent_app import dataset_import

    taken = []
    monkeypatch.setattr(
        dataset_import, "import_written", lambda db, body, by: taken.append(body.path)
    )
    samples = tmp_path / "samples"
    samples.mkdir()
    monkeypatch.setattr(dataset_import, "SAMPLES", samples)
    monkeypatch.setattr(dataset_import, "APP", tmp_path)
    own = Database(tmp_path / "agent.db")
    dataset_import.take_in_samples(own)
    assert taken == [str(samples)]
    own.close()
    dataset_import.take_in_samples(Database(tmp_path / "agent.db"))
    dataset_import.take_in_samples(Database(tmp_path / "other.db"))
    assert taken == [str(samples)]
