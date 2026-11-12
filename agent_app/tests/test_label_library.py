"""The labels of the whole library (definition 26.1; 25.4: the same label had another
requirement key in every dataset, so the same images were never one requirement)."""

import json

import pytest
from agent_app.errors import ApiError
from agent_app.instructions import latest_row
from test_runs import DEFINITIONS, save_version, scenario


def _latest(db, dataset):
    row = latest_row(db, dataset)
    return row["requirement_key"], json.loads(row["payload_json"])["label_definitions"]


async def _dataset(app, client, ids, definitions):
    dataset = (
        await client.post(
            "/v1/datasets",
            json={"name": "円の2", "purpose": "円", "image_ids": list(ids.values())},
        )
    ).json()["id"]
    save_version(
        app.state.db, dataset, {"text": "円を囲む", "label_definitions": definitions}
    )
    return dataset


def test_the_same_name_is_one_label_of_the_library(tmp_path, monkeypatch):
    async def body(app, client, dataset, ids):
        db = app.state.db
        here_key, (circle,) = _latest(db, dataset)
        # The library's name, written another way, is the same label and requirement.
        other = await _dataset(
            app, client, ids, [{**DEFINITIONS[0], "name": "ｃｉｒｃｌｅ "}]
        )
        other_key, (same,) = _latest(db, other)
        assert (same["id"], same["name"], other_key) == (
            circle["id"],
            "circle",
            here_key,
        )
        # A new label enters the library when a version has it, not when a draft does.
        square = {"name": "四角", "shape": "bbox"}
        await client.put(
            f"/v1/datasets/{other}/drafts/instruction",
            json={"text": "円と四角", "label_definitions": [*DEFINITIONS, square]},
        )
        labels = (await client.get("/v1/labels")).json()["items"]
        assert [(i["name"], i["datasets"]) for i in labels] == [("circle", 2)]
        save_version(
            db, other, {"text": "円と四角", "label_definitions": [*DEFINITIONS, square]}
        )
        labels = (await client.get("/v1/labels")).json()["items"]
        assert sorted(i["name"] for i in labels) == ["circle", "四角"]
        # Two names the library finds as one are one label twice.
        with pytest.raises(ApiError) as twice:
            save_version(
                db, other, {"label_definitions": [square, {**square, "name": " 四角"}]}
            )
        assert twice.value.details["reason"] == "duplicate_labels"

    scenario(tmp_path, monkeypatch, body)
