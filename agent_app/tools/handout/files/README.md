# LLM Agents for Image Annotation (version {version})

日本語はこの下にあります。

An app that puts annotations on images: boxes and outlines around objects, and the values read from them.
Ask the agents (Guide and Steward) in the talk on the left. The AI makes the annotations, and you check and fix them on the right.

## What you need

- Windows, Mac or Linux.
- **Claude Code** (the `claude` command) or **Codex** (the `codex` command), installed and signed in. The AI runs through that CLI, and its use counts toward your own subscription.
- Mac and Linux: internet, the first time only. Windows: not needed, as Python and the libraries are in the zip.

## Start

1. Extract the whole zip to a folder of your choice. It can't be opened from inside the zip.
2. Start it.
   - Windows: double-click `Annotation.exe` (a white frame on an indigo square), every time.
   - Mac and Linux: in a terminal, go into this folder and run `sh start.sh`. The first time, it installs uv and Python into this folder, which takes a few minutes and needs internet.
   - Windows: the app's window opens (Chrome, or Edge if there is no Chrome, with no address bar), and "Annotation" appears in the taskbar.
   - Mac and Linux: the app opens in your browser (usually http://127.0.0.1:3900/, or the next free number if another program uses it), and "Annotation" appears in the taskbar (Dock). The app runs for as long as that icon is there. Press it for a small window; if you closed the browser tab, [Open in browser] opens it again.
3. Quit.
   - Windows: close the app's window. Any AI annotation stops, and the app quits.
   - Mac and Linux: press the icon and then [Quit] in the small window.
   - Both: the power icon at the top right of the screen also quits. Quit before you delete the folder.

- On Windows, if you see "Windows protected your PC", press "More info" and then "Run anyway".
- On Mac and Linux, if you moved the folder after the first start, delete `.venv` (in `agent_app`) in it before you start again.

## The datasets inside

{datasets_en}

In a dataset with nothing done yet, ask the Steward on the left "How do I use this?" and it tells you where to begin.
To try your own images, use "Take in" at the top right of the library to make a dataset from a folder of images.

## Models

At first, both the agents and the annotation use Claude Opus 5.5. If you only use Codex, choose a GPT model in the settings at the top right.

## Language

The screen is in English or Japanese. It opens in your browser's language, and you can switch it in the settings at the top right. The agents answer in the language you write in.

## Where the data is, and new versions

- What you make stays in this folder (`agent_app/agent.db` and `agent_app/agent-files/`).
- For a new version, delete this folder and extract the new one. Earlier data is not carried over.
- To keep a dataset, write it out to a folder first with "Write out" in the library.

## Trouble and feedback

Please send the message or what you saw on the screen, along with `agent_app/server.log` in this folder (the app's log), to this app's author, or open an issue: https://github.com/microtaro/llm-agents-for-image-annotation/issues

---

# LLM Agents for Image Annotation（version {version}）

画像にアノテーション（物を囲む枠・輪郭と、読み取った値）を付けるアプリです。
左の会話で係（受付・担当）に頼むと、AI がアノテーションを作り、人は右の画面で確かめて直します。

## 要る物

- Windows、Mac、Linux のどれか。
- **Claude Code**（`claude` のコマンド）か **Codex**（`codex` のコマンド）が入っていて、ログインしてある事。AI はこの CLI で動きます（費用は、それぞれのサブスクリプションの範囲です）。
- Mac・Linux は、初めて入れる時だけインターネット。Windows は、Python と使うライブラリが zip に入っているので要りません。

## 入れ方と起こし方

1. zip を全部、好きな場所のフォルダに展開します（zip の中から直接は開けません）。
2. 起こす
   - Windows: `Annotation.exe`（藍紫の四角に白い枠の印）をダブルクリック。2回目からも同じです。
   - Mac・Linux: ターミナルでこのフォルダに入り、`sh start.sh`。
   - Mac・Linux は、初めての時だけ uv と Python をこのフォルダの中に入れてから起きます（数分かかり、インターネットが要ります）。Windows はすぐ起きます。
   - Windows: 起きると、アプリの窓（Chrome、無ければ Edge で開く、アドレス欄の無い窓）が開き、タスクバーに「Annotation」の印が並びます。
   - Mac・Linux: 起きると、ブラウザでアプリの画面（ふつうは http://127.0.0.1:3900/ 。その番号を別のソフトが使っている時は次の空き番号）が開き、タスクバー（Dock）に「Annotation」の印が並びます。この印がある間が、アプリが動いている間です。印を押すと小さな窓が開き、ブラウザのタブを閉じた時は、その［ブラウザで開く］で、もう一度開けます。
3. 終了する
   - Windows: アプリの窓を閉じます。AI のアノテーションの途中でも止まって、アプリが終わります。
   - Mac・Linux: 印を押して開く小さな窓の［終了］を押します。
   - どちらも、画面の右上の電源の印でも終了します。フォルダを消す時は、先に終了してください。

- Windows で「Windows によって PC が保護されました」と出た時は、「詳細情報」→「実行」を押してください。
- Mac・Linux で、起きた後にフォルダを別の場所へ動かした時は、そのフォルダの中の `.venv`（`agent_app` の中）を消してから起こしてください。

## 初めに入っているデータセット

{datasets}

何もしていないデータセットは、左の担当に「使い方おしえて」と頼むと、何から始めればいいかを答えます。
自分の画像でも試せます。ライブラリの右上の「取り込む」で、画像のフォルダからデータセットを作ります。

## 使うモデル

初めは、係もアノテーションも Claude Opus 5.5 です。Codex だけを使っている人は、右上の設定で GPT のモデルを選んでください。

## 言語

画面は日本語と英語です。ブラウザの言語で開き、右上の設定で切り替えられます。係は、あなたが書いた言語で答えます。

## データの置き場と、新しい版

- 作ったデータは、このフォルダの中（`agent_app/agent.db` と `agent_app/agent-files/`）に残ります。
- 新しい版をもらった時は、このフォルダごと消してから、新しい物を展開してください。前のデータは引き継ぎません。
- 残したいデータセットは、消す前にライブラリの「書き出す」で、フォルダに書き出しておけます。

## 困った時・感想

表示されたメッセージや画面の様子と、このフォルダの `agent_app/server.log`（アプリの記録）を、このアプリの作者に送るか、Issue を開いてください: https://github.com/microtaro/llm-agents-for-image-annotation/issues
