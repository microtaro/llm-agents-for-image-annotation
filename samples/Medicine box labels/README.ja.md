[English](README.md) | **日本語**

# データセットの書き出し（このアプリの形・形の版 6）

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

- `format`: いつも `"agent-app-dataset"`。`version`: 形の版（この説明は 6）。
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
