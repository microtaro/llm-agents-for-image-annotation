**English** | [Japanese](README.ja.md)

# Dataset written out (this app's form, version 6)

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

- `format`: always `"agent-app-dataset"`. `version`: the form's version (6 here).
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
