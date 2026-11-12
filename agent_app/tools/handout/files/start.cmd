@echo off
rem The start on Windows from a clone (user 2026-11-11: the public repository has no zip; run it
rem with Git alone, no Node.js, by double-click). As start.sh does, the first time it puts uv of
rem this version, Python and uv's cache in this folder, then hands over to the launcher with no
rem terminal (agent_app.launch), which also makes the shortcut "Annotation" here for the next
rem starts. It speaks the machine's language, told by its code page (932: Japanese).
setlocal
for /f "tokens=2 delims=:" %%c in ('chcp') do set "CODEPAGE=%%c"
set "CODEPAGE=%CODEPAGE: =%"
chcp 65001 >nul
cd /d "%~dp0"
set "HERE=%CD%"
if "%CODEPAGE%"=="932" (
  set "SAY_FIRST=初めての起動: uv と Python とライブラリをこのフォルダに入れます。数分かかります。"
  set "SAY_UV=1/3 uv を入れています…"
  set "SAY_PYTHON=2/3 Python を入れています…"
  set "SAY_LIBRARIES=3/3 ライブラリを入れています…"
  set "SAY_STARTING=アプリを起こしています。アプリの窓が開きます。次からは、このフォルダの Annotation をダブルクリックしてください。"
  set "SAY_MISPLACED=このファイルは、アプリのフォルダの中で開いてください。"
  set "SAY_FAILED=起きませんでした。上の表示を、このアプリの作者に送ってください。"
) else (
  set "SAY_FIRST=First start: installing uv, Python and the libraries into this folder. This takes a few minutes."
  set "SAY_UV=1/3 Installing uv…"
  set "SAY_PYTHON=2/3 Installing Python…"
  set "SAY_LIBRARIES=3/3 Installing the libraries…"
  set "SAY_STARTING=Starting the app. Its window opens. Next time, double-click Annotation in this folder."
  set "SAY_MISPLACED=Open this file inside the app's folder."
  set "SAY_FAILED=The app did not start. Please send the lines above to this app's author."
)
if not exist "%HERE%\agent_app\pyproject.toml" goto misplaced
rem UV_SYSTEM_CERTS: the certificates Windows trusts (an antivirus or proxy that looks into HTTPS).
set "UV_INSTALL_DIR=%HERE%\uv"
set "UV_NO_MODIFY_PATH=1"
set "UV_DISABLE_UPDATE=1"
set "UV_PYTHON_INSTALL_DIR=%HERE%\python"
set "UV_CACHE_DIR=%HERE%\uv-cache"
set "UV_MANAGED_PYTHON=1"
set "UV_PYTHON_DOWNLOADS=automatic"
set "UV_SYSTEM_CERTS=1"
set "FIRST="
if exist "%HERE%\uv\uv.exe" goto installed
set "FIRST=1"
echo %SAY_FIRST%
echo %SAY_UV%
rem uv's installer's own words go to a log, shown only when it fails (2026-11-11: its
rem "everything's installed!" came before Python and the libraries).
set "UV_LOG=%HERE%\uv-install.log"
powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/0.13.6/install.ps1 | iex *> $env:UV_LOG"
if errorlevel 1 (
  type "%UV_LOG%"
  goto failed
)
:installed
if defined FIRST echo %SAY_PYTHON%
"%HERE%\uv\uv.exe" --quiet --directory agent_app python install --no-bin
if errorlevel 1 goto failed
if defined FIRST echo %SAY_LIBRARIES%
"%HERE%\uv\uv.exe" --quiet sync --project agent_app --locked --no-dev
if errorlevel 1 goto failed
start "" "%HERE%\agent_app\.venv\Scripts\pythonw.exe" -m agent_app.launch
rem The first time, the words about the shortcut stay a moment before this window closes.
if defined FIRST (
  echo %SAY_STARTING%
  ping -n 6 127.0.0.1 >nul
)
exit /b 0
:misplaced
echo %SAY_MISPLACED%
pause
exit /b 1
:failed
echo %SAY_FAILED%
pause
exit /b 1
