"""Writing datasets out to a folder (definition 60.4): no decision, nothing in the app changes.

Each dataset goes into a new folder named after it under the folder given (never over another:
a name taken gets " (2)", " (3)"...), written whole under a hidden name first and renamed at the
end, so a failure leaves nothing half written.

- This app's form (to give the dataset to another person using the app, and for other software
  to read, definitions 60.13 and 60.14): dataset.json (the mark FORMAT and its VERSION, the
  dataset, the plan's labels and each image's annotation now with its objects, JSON as it is:
  what other software reads), app.json (the same mark; under "app" every table this app takes
  in again whole, its history), images/ (the original files), masks/ (the masks, by their
  SHA-256), README.md and README.ja.md (what is where, in English and in Japanese).
- COCO (to open and analyse in other tools, COCO Annotator and the like): annotations.json with
  images/ when the files go too. Each image's annotation is what training uses, or its annotation
  now (by the latest version saved, as the library's card counts it, image_state.py); only the
  images that have one are in it, an image with no object being one found empty (COCO says an
  image with no annotation is a negative; 2026-10-30: one left out or not annotated yet was one
  too). Every image and its state is this app's form; categories
  by the library's names now; a box is bbox, an outline segmentation, a mask RLE, a label's
  values attributes.
"""

import json
import re
import shutil
import uuid
from itertools import groupby
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request
from PIL import Image
from pydantic import Field

from .adoption import adoption
from .annotation_sets import current
from .datasets import dataset_row, image_rows
from .db import now
from .drafts import plan_draft
from .errors import ApiError, Model
from .image_state import image_states
from .images import IMAGE_FORMATS
from .instructions import latest_basis, latest_revision, version_rows
from .label_ids import names_now
from .run_queries import dataset_results, dataset_runs, result_row
from .system import FOLDER_EXAMPLE, THIS_COMPUTER

router = APIRouter(prefix="/v1")

FORMAT = "agent-app-dataset"
# 3 (10-28): the files of images its records name that it no longer holds (record_images).
# 4 (10-29): the app's history in its own app.json; an object's id in its image, and its parent
# by that id (a number is per label, so "parent: 1" could be several objects).
# 5 (10-30): what a person checked by a version's criteria (confirmations; definition 85.5).
# 6 (10-30): label changes are copies (copies, copy_results; definition 85.15).
VERSION = 6


# What the folder holds, for whoever reads it with other software (definition 60.13), one file
# per language as the public repository's README (2026-11-10: in one file, the part in the other
# language came first, garbled or unreadable to whoever opened it). The form's version is VERSION.
README_EN = """**English** | [Japanese](README.ja.md)

# Dataset written out (this app's form, version <VERSION>)

This folder is one dataset written out by the annotation app. To read it with other software,
`dataset.json` is all you need. `app.json` is what this app takes in again with its history;
you can leave it unread.

## Files

- `dataset.json`: the dataset's annotation now (below), UTF-8 JSON.
- `app.json`: this app's history (every version and the draft of the plan, every record of the AI and of people, what training uses), read when this app takes the folder in.
- `images/`: the original image files, as taken in; also those of images its records name that were taken out of the dataset later (not in the top part's `images`).
- `masks/`: mask PNGs, named by their SHA-256.
- `README.md`: this text, and `README.ja.md` the same in Japanese.

## dataset.json

- `format`: always `"agent-app-dataset"`. `version`: the form's version (<VERSION> here).
- `dataset`: `name`, `purpose`.
- `labels`: the labels of the plan's latest version (the draft when there is none).
  - `name`, `shape` (`bbox`, `polygon`, or `image`: one answer for the whole image), `parent` (the name of the label this one is a part of, else null), `description`.
  - `attributes`: the label's values. `name`, `type` (`text`, `number`, `choice`), `choices`, `description`.
- `images`: one per image, in the dataset's order.
  - `file` (relative to this folder), `name`, `width`, `height` (pixels).
  - `used_for_training`: whether training uses it (true / false).
  - `annotation`: the image's annotation now: of the results in the output form of the plan's latest version (labels, shapes, parents, values), the one a person chose, else the newest success, what the app's library counts as annotated. A result of an earlier version is in when its output form is the same. null when there is none yet.
    - `record`: the record's number. `by`: `ai`, `human` (a person's fix) or `import` (taken in). `model`: the AI's model (for `ai`). `version`: the plan's version the result was made by.
    - `objects`: `id` (one only in its image), `number` (per label, the 2 of "box 2" on the app's screens), `label`, `geometry`, `attributes` (name to text or number, or null), `parent` (the parent object's `id`, else null).
    - An object of a label of shape `image` (one answer for the whole image) is written as a box over the whole image; the answer is in `attributes`.

## Shapes and coordinates

Coordinates are the original image's pixels, the origin at the top left (x to the right, y
down); they may have decimals.

- Box: `{"type": "bbox", "xywh": [x, y, width, height]}`
- Outline: `{"type": "polygon", "points": [[x, y], ...]}` (one closed exterior; the first point is not repeated at the end)
- Mask: `{"type": "mask", "file": "masks/<sha256>.png", "bbox_xywh": [x, y, width, height]}`; the PNG is 8-bit grey of the image's size, 0 the background and 255 the object.
""".replace("<VERSION>", str(VERSION))
README_JA = """[English](README.md) | **日本語**

# データセットの書き出し（このアプリの形・形の版 <VERSION>）

このフォルダは、アノテーションのアプリが1つのデータセットを書き出した物です。
ほかのソフトで読む時は、`dataset.json` だけを読めば足ります。
`app.json` は、このアプリが履歴ごと取り込み直すための物で、読まなくてかまいません。

## ファイル

- `dataset.json`: データセットの今のアノテーション（下の形）。UTF-8 の JSON。
- `app.json`: このアプリの履歴（計画書の全部の版と下書き、AI と人の全部の記録、学習に使う物の選び）。このアプリが取り込む時に読む。
- `images/`: 元の画像のファイル（取り込んだ時のまま）。記録が名指す、後でデータセットから取り除いた画像のファイルも入る（上の部分の `images` には出ない）。
- `masks/`: 塗り（mask）の PNG。名前は中身の SHA-256。
- `README.ja.md`: この説明。`README.md` は同じ物の英語。

## dataset.json

- `format`: いつも `"agent-app-dataset"`。`version`: 形の版（この説明は <VERSION>）。
- `dataset`: `name`（名前）、`purpose`（目的）。
- `labels`: 計画書の最新の版のラベル（版が無ければ下書き）。
  - `name`、`shape`（`bbox` 枠、`polygon` 輪郭、`image` 画像全体への答え）、`parent`（このラベルが部分である親のラベルの名前、無ければ null）、`description`。
  - `attributes`: ラベルの値の定義。`name`、`type`（`text`・`number`・`choice`）、`choices`（`choice` の選択肢）、`description`。
- `images`: 画像ごとに1つ（データセットの並びの順）。
  - `file`（このフォルダからの相対パス）、`name`、`width`、`height`（画素）。
  - `used_for_training`: 学習に使っているか（true / false）。
  - `annotation`: 画像の今のアノテーション。計画書の最新の版と同じ出力の形（ラベル・形・親・値の定義）の結果のうち、人が選んだ結果、無ければ一番新しい成功（アプリのライブラリで「アノテーション済み」と数える物）。前の版で作った結果も、出力の形が同じなら入る。まだ無ければ null。
    - `record`: 記録の番号。`by`: 作ったもの（`ai` AI、`human` 人の直し、`import` 取り込み）。`model`: AI のモデル（AI の時だけ）。`version`: その結果を作った計画書の版。
    - `objects`: 物の一覧。`id`（その画像の中で1つだけの番号）、`number`（ラベルごとの番号。アプリの画面の「箱 2」の 2）、`label`、`geometry`、`attributes`（ラベルの値。名前 → 文字か数、無ければ null）、`parent`（親の物の `id`、無ければ null）。
    - 形が `image`（画像全体への答え）のラベルの物は、画像全体を囲む枠で書く。答えは `attributes` にある。

## 形と座標

座標は元画像の画素、左上が原点（x は右、y は下へ増える）。小数もある。

- 枠: `{"type": "bbox", "xywh": [x, y, 幅, 高さ]}`
- 輪郭: `{"type": "polygon", "points": [[x, y], ...]}`（閉じた1つの外周。最初の点を最後に繰り返さない）
- 塗り: `{"type": "mask", "file": "masks/<sha256>.png", "bbox_xywh": [x, y, 幅, 高さ]}`。PNG は画像と同じ大きさの8ビットのグレー、0 が背景、255 が物。
""".replace("<VERSION>", str(VERSION))


class ExportInput(Model):
    dataset_ids: list[str] = Field(min_length=1, max_length=200)
    format: Literal["app", "coco"] = Field(
        "app",
        description="app: this app's form, to give to another person using it; coco: COCO's"
        " JSON, to open and analyse in other tools.",
    )
    dest: str = Field(
        min_length=1,
        max_length=4096,
        description=f"A folder {THIS_COMPUTER} that is there already, as it writes them (e.g."
        f" {FOLDER_EXAMPLE}); each dataset gets a new folder in it.",
    )
    which: Literal["used", "now"] = Field(
        "used",
        description="COCO: each image's annotation is what training uses, or its annotation"
        " now (as annotating with AI shows it); only the images that have one go.",
    )
    images: bool = Field(True, description="COCO: the image files go too (images/).")


def _rows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql, args)]


def _folder(dest, name):
    """A new folder's path under dest named after the dataset, never one there already."""
    base = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .") or "dataset"
    path, n = dest / base, 1
    while path.exists():
        n += 1
        path = dest / f"{base} ({n})"
    return path


def _file_names(images):
    """{image id: its file name in images/}: its own name, once each (a name met again gets the
    next number not taken before its suffix; review 2026-10-28 B#2: its place made a name another
    image had, and one file was written over the other)."""
    names, taken = {}, set()
    for image in images:
        name = Path(image["name"]).name or image["id"]
        stem, suffix, n = Path(name).stem, Path(name).suffix, 1
        while name in taken:
            n += 1
            name = f"{stem}-{n}{suffix}"
        taken.add(name)
        names[image["id"]] = name
    return names


def _copy_image(db, image, to):
    extension, _ = IMAGE_FORMATS[image["format"]]
    source = db.files.path("images", image["id"].removeprefix("img-"), extension)
    shutil.copyfile(source, to)


def _decoded(row):
    """A row with its JSON columns (*_json) as the JSON they hold, not as strings."""
    return {
        k: json.loads(v) if k.endswith("_json") and isinstance(v, str) else v
        for k, v in row.items()
    }


def _readable_geometry(annotation):
    """An object's shape for other software: a box's xywh, an outline's points, or a mask's
    PNG file (masks/) with the box around it."""
    geometry = annotation["geometry"]
    if geometry["type"] == "mask":
        return {
            "type": "mask",
            "file": f"masks/{annotation['mask_sha256']}.png",
            "bbox_xywh": geometry["bbox_xywh"],
        }
    return geometry


def _readable(db, dataset_id, images, files, plan):
    """What other software reads (definition 60.13): the plan's labels, and each image's
    annotation now by the latest version saved (as the library's card counts it, the rule
    applied, image_state.py) with whether training uses it; JSON as it is, no ids of the
    app."""
    used = {}
    if latest_revision(db, dataset_id) is not None:
        used = {
            i["image_id"]: i["source"] == "result"
            for i in adoption(db, dataset_id)["items"]
        }
    _, states = image_states(db, dataset_id, *latest_basis(db, dataset_id))
    name = names_now(db, dataset_id)
    readable = []
    for image in images:
        now_result = (states.get(image["id"]) or {}).get("now")
        annotation = None
        if now_result:
            row = result_row(db, now_result["result_id"])
            objects = current(db, row["set_id"])
            # An object's id in its image (definition 60.14): numbers are per label.
            ids = {a["id"]: n for n, a in enumerate(objects, start=1)}
            settings = json.loads(row["settings_json"]) if row["settings_json"] else {}
            annotation = {
                "record": row["record_number"],
                "by": row["result_by"],
                "model": settings.get("model"),
                "version": row["instruction_revision"],
                "objects": [
                    {
                        "id": ids[a["id"]],
                        "number": a["number"],
                        "label": name(row["instruction_revision"], a["label"]),
                        "geometry": _readable_geometry(a),
                        "attributes": a["attributes"],
                        "parent": ids.get(a["parent_id"]),
                    }
                    for a in objects
                ],
            }
        readable.append(
            {
                "file": f"images/{files[image['id']]}",
                "name": image["name"],
                "width": image["width"],
                "height": image["height"],
                "used_for_training": used.get(image["id"], False),
                "annotation": annotation,
            }
        )
    labels = [
        {
            "name": d["name"],
            "shape": d["shape"],
            "parent": d.get("parent"),
            "description": d.get("description") or "",
            "attributes": [
                {
                    "name": a["name"],
                    "type": a["type"],
                    "choices": a.get("choices"),
                    "description": a.get("description") or "",
                }
                for a in d.get("attributes") or []
            ],
        }
        for d in (plan or {}).get("label_definitions") or []
    ]
    return labels, readable


def _write_app(db, dataset_id, folder):
    """This app's form, read by other software too (definitions 60.13, 60.14): dataset.json the
    dataset, the plan's labels and each image's annotation now (JSON as it is); app.json under
    "app" what this app takes in again whole (no talk, no decisions), its JSON columns as JSON;
    README.md and README.ja.md say it."""
    dataset = dict(dataset_row(db, dataset_id))
    images = [dict(r) for r in image_rows(db, dataset_id)]

    def rows(sql, args=()):
        return [_decoded(r) for r in _rows(db, sql, args)]

    # The results of its records, whichever kind (result_records, definition 21.4, 60.11).
    columns = db.columns("results")
    results = [
        {k: r[k] for k in r if k in columns}
        for r in (_decoded(dict(x)) for x in dataset_results(db, dataset_id))
    ]
    # Images its records name that it no longer holds (taken out later): their files go too,
    # so its records are taken in whole, but they are not its images (review 2026-10-28 B#5:
    # such a folder could not be taken in where the image was not in the library).
    held = {i["id"] for i in images}
    record_images = [
        dict(db.one("SELECT * FROM images WHERE id=?", (image_id,)))
        for image_id in dict.fromkeys(r["image_id"] for r in results)
        if image_id not in held
    ]
    files = _file_names([*images, *record_images])
    sets = [
        _decoded(
            dict(db.one("SELECT * FROM annotation_sets WHERE id=?", (r["set_id"],)))
        )
        for r in results
    ]
    annotations = [
        a
        for s in sets
        for a in rows(
            "SELECT * FROM annotations WHERE set_id=? ORDER BY rowid", (s["id"],)
        )
    ]
    instructions = [_decoded(dict(r)) for r in version_rows(db, dataset_id)]
    drafts = [_decoded(dict(r)) for r in (plan_draft(db, dataset_id),) if r]
    # The library's labels the plans name (a label is one for every dataset, definition 26.1).
    label_ids = {
        d["id"]
        for row in instructions + drafts
        for d in row["payload_json"].get("label_definitions", [])
        if d.get("id")
    }
    library_labels = [
        dict(r)
        for r in db.execute("SELECT * FROM labels ORDER BY name_key")
        if r["id"] in label_ids
    ]
    images_dir = folder / "images"
    images_dir.mkdir()
    for image in [*images, *record_images]:
        _copy_image(db, image, images_dir / files[image["id"]])
    masks = {a["mask_sha256"] for a in annotations if a["mask_sha256"]}
    if masks:
        (folder / "masks").mkdir()
        for sha in masks:
            shutil.copyfile(
                db.files.find("masks", sha), folder / "masks" / f"{sha}.png"
            )
    # The labels and each image's annotation now by the latest version saved, as the library's
    # card counts them; a draft being written changes nothing written out (user 2026-10-28).
    plan = instructions[-1]["payload_json"] if instructions else {}
    labels, readable = _readable(db, dataset_id, images, files, plan)
    mark = {"format": FORMAT, "version": VERSION, "exported_at": now()}
    document = {
        **mark,
        "dataset": {"name": dataset["name"], "purpose": dataset["purpose"]},
        "labels": labels,
        "images": readable,
    }
    history = {
        **mark,
        "app": {
            "dataset": dataset,
            "library_labels": library_labels,
            "images": [
                {**_decoded(image), "file": f"images/{files[image['id']]}"}
                for image in images
            ],
            "record_images": [
                {**_decoded(image), "file": f"images/{files[image['id']]}"}
                for image in record_images
            ],
            "instructions": instructions,
            "drafts": drafts,
            "recipes": rows("SELECT * FROM recipes WHERE dataset_id=?", (dataset_id,)),
            "runs": [_decoded(dict(r)) for r in dataset_runs(db, dataset_id)],
            "fixes": rows(
                "SELECT * FROM fixes WHERE dataset_id=? ORDER BY number", (dataset_id,)
            ),
            "imports": rows(
                "SELECT * FROM imports WHERE dataset_id=? ORDER BY number",
                (dataset_id,),
            ),
            # Copies (label changes and results carried over; definition 79, 85.15) and what
            # each result of theirs was copied from.
            "copies": rows(
                "SELECT * FROM copies WHERE dataset_id=? ORDER BY number",
                (dataset_id,),
            ),
            "copy_results": rows(
                "SELECT cr.* FROM copy_results cr JOIN results r ON r.id=cr.result_id"
                " JOIN copies c ON c.id=r.copy_id WHERE c.dataset_id=?",
                (dataset_id,),
            ),
            "results": results,
            "annotation_sets": sets,
            "annotations": annotations,
            "uses": rows(
                "SELECT * FROM uses WHERE dataset_id=? ORDER BY id", (dataset_id,)
            ),
            "confirmations": rows(
                "SELECT * FROM confirmations WHERE dataset_id=? ORDER BY confirmed_at",
                (dataset_id,),
            ),
            "training_snapshots": rows(
                "SELECT * FROM training_snapshots WHERE dataset_id=?", (dataset_id,)
            ),
            "label_colors": rows(
                "SELECT * FROM label_colors WHERE dataset_id=?", (dataset_id,)
            ),
        },
    }
    for file, content in (("dataset.json", document), ("app.json", history)):
        (folder / file).write_text(
            json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    (folder / "README.md").write_text(README_EN, encoding="utf-8")
    (folder / "README.ja.md").write_text(README_JA, encoding="utf-8")
    # The annotations now (as the cards count them) apart from all its records' (the reception's
    # test 2026-10-29: "41" was every record's, read as the dataset's).
    return {
        "images": len(images),
        "annotations": sum(
            len((i["annotation"] or {}).get("objects") or []) for i in readable
        ),
        "annotations_in_records": len(annotations),
    }


def _rle(mask_path):
    """A mask as COCO's uncompressed run-length: column by column, starting with the off."""
    with Image.open(mask_path) as mask:
        pixels = mask.convert("L").transpose(Image.Transpose.TRANSPOSE).tobytes()
        width, height = mask.size
    counts, on = [], False
    for value, run in groupby(pixels, key=lambda p: p > 127):
        if value != on:
            counts.append(0)
        counts.append(sum(1 for _ in run))
        on = not value
    return {"size": [height, width], "counts": counts}, sum(p > 127 for p in pixels)


def _coco_annotation(db, annotation, number, image_number, category):
    geometry = annotation["geometry"]
    found = {
        "id": number,
        "image_id": image_number,
        "category_id": category,
        "iscrowd": 0,
        "attributes": annotation["attributes"],
    }
    if geometry["type"] == "bbox":
        x, y, w, h = geometry["xywh"]
        return {**found, "bbox": [x, y, w, h], "area": w * h, "segmentation": []}
    if geometry["type"] == "polygon":
        points = geometry["points"]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        area = (
            abs(
                sum(
                    xs[i] * ys[(i + 1) % len(points)]
                    - xs[(i + 1) % len(points)] * ys[i]
                    for i in range(len(points))
                )
            )
            / 2
        )
        return {
            **found,
            "bbox": [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)],
            "area": area,
            "segmentation": [[c for p in points for c in p]],
        }
    rle, area = _rle(db.files.find("masks", annotation["mask_sha256"]))
    return {**found, "bbox": geometry["bbox_xywh"], "area": area, "segmentation": rle}


def _write_coco(db, dataset_id, folder, which, with_images):
    """COCO's JSON: the images that have an annotation (what training uses, or its annotation
    now) and their objects."""
    images = [dict(r) for r in image_rows(db, dataset_id)]
    if which == "used":
        chosen = {
            i["image_id"]: i.get("result_id") for i in adoption(db, dataset_id)["items"]
        }
    else:
        # By the latest version saved, as the library's card counts it (definition 60.13).
        _, states = image_states(db, dataset_id, *latest_basis(db, dataset_id))
        chosen = {k: (s["now"] or {}).get("result_id") for k, s in states.items()}
    images = [i for i in images if chosen.get(i["id"])]
    files = _file_names(images)
    name = names_now(db, dataset_id)
    categories, coco_images, coco_annotations = {}, [], []
    for number, image in enumerate(images, start=1):
        coco_images.append(
            {
                "id": number,
                "file_name": files[image["id"]],
                "width": image["width"],
                "height": image["height"],
            }
        )
        record = result_row(db, chosen[image["id"]])
        annotations = current(db, record["set_id"])
        numbers = {
            a["id"]: len(coco_annotations) + i + 1 for i, a in enumerate(annotations)
        }
        for annotation in annotations:
            label = name(record["instruction_revision"], annotation["label"])
            category = categories.setdefault(label, len(categories) + 1)
            found = _coco_annotation(
                db, annotation, numbers[annotation["id"]], number, category
            )
            if annotation["parent_id"] in numbers:
                # The object it is a part of (not in COCO; other tools pass it by).
                found["parent_id"] = numbers[annotation["parent_id"]]
            coco_annotations.append(found)
    if with_images:
        (folder / "images").mkdir()
        for image in images:
            _copy_image(db, image, folder / "images" / files[image["id"]])
    dataset = dataset_row(db, dataset_id)
    document = {
        "info": {
            "description": f"{dataset['name']}: {dataset['purpose']}",
            "date_created": now(),
        },
        "images": coco_images,
        "annotations": coco_annotations,
        "categories": [
            {"id": number, "name": label, "supercategory": ""}
            for label, number in categories.items()
        ],
    }
    (folder / "annotations.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )
    return {"images": len(images), "annotations": len(coco_annotations)}


def export_datasets(db, body: ExportInput):
    """Each dataset into a new folder under body.dest, in the form asked; what was written."""
    dest = Path(body.dest).expanduser()
    if not dest.is_absolute() or not dest.is_dir():
        raise ApiError(
            422,
            "export_dest_missing",
            "The folder to write into does not exist",
            {"dest": body.dest},
        )
    for dataset_id in body.dataset_ids:
        dataset_row(db, dataset_id)
    written = []
    for dataset_id in body.dataset_ids:
        name = dataset_row(db, dataset_id)["name"]
        folder = _folder(dest, name)
        part = dest / f".{folder.name}.{uuid.uuid4().hex[:8]}.part"
        part.mkdir()
        try:
            # Each read takes the database's lock itself; copying the files holds none, so the
            # app goes on while a large dataset is written.
            counts = (
                _write_app(db, dataset_id, part)
                if body.format == "app"
                else _write_coco(db, dataset_id, part, body.which, body.images)
            )
            part.rename(folder)
        except OSError as exc:
            shutil.rmtree(part, ignore_errors=True)
            raise ApiError(
                500,
                "export_failed",
                "The dataset could not be written",
                {"dataset": name},
            ) from exc
        except BaseException:
            shutil.rmtree(part, ignore_errors=True)
            raise
        written.append(
            {"dataset_id": dataset_id, "name": name, "path": str(folder), **counts}
        )
    return {"format": body.format, "dest": str(dest), "written": written}


@router.post("/library/export")
def export_route(request: Request, body: ExportInput):
    return export_datasets(request.app.state.db, body)
