#!/bin/sh
# The one thing a person runs (user 2026-10-29: install and then start was one step too many):
# the first time it puts uv of this version, Python and uv's cache in this folder (an older uv
# on the machine did not know Python 3.14.7; deleting the folder deletes it all), then the
# launcher (agent_app.launch) starts the app in the background and opens the browser (the app
# quits from its screen).
cd "$(dirname "$0")"
HERE="$(pwd)"
# A line in the machine's language, as the launcher's (launch.launcher_words).
say() {
  case "${LC_ALL:-${LANG:-}}" in
    ja*) echo "$1" ;;
    *) echo "$2" ;;
  esac
}
if [ ! -f "$HERE/agent_app/pyproject.toml" ]; then
  say "zip を全部フォルダに展開してから、そこで sh start.sh を流してください。" \
    "Extract the whole zip into a folder first, then run sh start.sh there."
  exit 1
fi
# UV_DISABLE_UPDATE: no install receipt outside the folder (2026-10-29: it pointed at this folder,
# over the machine's own uv).
export UV_INSTALL_DIR="$HERE/uv" UV_NO_MODIFY_PATH=1 UV_DISABLE_UPDATE=1 \
  UV_PYTHON_INSTALL_DIR="$HERE/python" UV_CACHE_DIR="$HERE/uv-cache" UV_MANAGED_PYTHON=1 \
  UV_PYTHON_DOWNLOADS=automatic \
  UV_SYSTEM_CERTS=1
# UV_SYSTEM_CERTS: the certificates the machine trusts (2026-10-30: an antivirus or proxy that
# looks into HTTPS had a certificate uv's own list did not know, "UnknownIssuer").
failed() {
  say "起きませんでした。上の表示を、このアプリの作者に送ってください。" \
    "The app did not start. Please send the lines above to this app's author."
  exit 1
}
# The first start says its steps; uv's installer's own words go to a log, shown only when it
# fails (2026-11-11: its "everything's installed!" came before Python and the libraries).
FIRST=
if [ ! -x "$HERE/uv/uv" ]; then
  FIRST=1
  say "初めての起動: uv と Python とライブラリをこのフォルダに入れます。数分かかります。" \
    "First start: installing uv, Python and the libraries into this folder. This takes a few minutes."
  say "1/3 uv を入れています…" "1/3 Installing uv…"
  curl -LsSf https://astral.sh/uv/0.13.6/install.sh | sh >"$HERE/uv-install.log" 2>&1 ||
    { cat "$HERE/uv-install.log"; failed; }
fi
[ -n "$FIRST" ] && say "2/3 Python を入れています…" "2/3 Installing Python…"
"$HERE/uv/uv" --quiet --directory agent_app python install --no-bin || failed
[ -n "$FIRST" ] && say "3/3 ライブラリを入れています…" "3/3 Installing the libraries…"
"$HERE/uv/uv" --quiet sync --project agent_app --locked --no-dev || failed
say "アプリを起こしています。小さな「Annotation」の窓とブラウザが開きます。その窓を閉じると、アプリが終了します。" \
  "Starting the app. A small \"Annotation\" window and your browser will open. Closing that window quits the app."
# The launcher: this folder's app running is opened, else the server starts apart on a free
# port, the browser opens and a small window stays while the app runs
# (agent_app/agent_app/launch.py, the one place).
exec "$HERE/agent_app/.venv/bin/python" -m agent_app.launch
