/* The zip's start on Windows, Annotation.exe (user 2026-10-30: the first start, start.cmd,
   opened a terminal; a .cmd always opens one, before its first line is read). A program with no
   console: it starts the launcher with this folder's Python, which has none either
   (python-windows\pythonw.exe -m agent_app.launch, in agent_app), and ends. Opened every time,
   so no shortcut is made, and the folder can move. Its mark is the app's (launcher.rc).
   Wide-character calls throughout, for a folder named in Japanese. build.py makes it with zig.
   What the launcher says itself is in agent_app/launch.py; this says only what stops it before. */
#include <windows.h>

#define MOST 32768

static void say(const wchar_t *ja, const wchar_t *en, DWORD error)
{
    wchar_t text[512];
    wsprintfW(text, PRIMARYLANGID(GetUserDefaultUILanguage()) == LANG_JAPANESE ? ja : en, error);
    MessageBoxW(NULL, text, L"Annotation", MB_OK | MB_ICONERROR);
}

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR arguments, int show)
{
    static wchar_t folder[MOST], python[MOST + 64], app[MOST + 64], command[MOST + 96];
    DWORD length = GetModuleFileNameW(NULL, folder, MOST);
    wchar_t *last = wcsrchr(folder, L'\\');
    if (length == 0 || length >= MOST || last == NULL) {
        say(L"このアプリの場所が分かりませんでした（エラー %lu）。このアプリの作者に伝えてください。",
            L"Could not find where this app is (error %lu). Please tell this app's author.",
            GetLastError());
        return 1;
    }
    *last = L'\0';
    lstrcpyW(python, folder);
    lstrcatW(python, L"\\python-windows\\pythonw.exe");
    lstrcpyW(app, folder);
    lstrcatW(app, L"\\agent_app");
    /* Opened from inside the zip, it is taken out alone: the rest is not beside it. */
    if (GetFileAttributesW(python) == INVALID_FILE_ATTRIBUTES) {
        say(L"zip の中身を全部、フォルダに展開してから、そこで Annotation.exe を開いてください。",
            L"Extract the whole zip into a folder first, then open Annotation.exe there.", 0);
        return 1;
    }
    lstrcpyW(command, L"\"");
    lstrcatW(command, python);
    lstrcatW(command, L"\" -m agent_app.launch");
    STARTUPINFOW start = {sizeof start};
    PROCESS_INFORMATION started;
    if (!CreateProcessW(python, command, NULL, NULL, FALSE, 0, NULL, app, &start, &started)) {
        say(L"アプリを起こせませんでした（エラー %lu）。このアプリの作者に伝えてください。",
            L"Could not start the app (error %lu). Please tell this app's author.",
            GetLastError());
        return 1;
    }
    CloseHandle(started.hThread);
    CloseHandle(started.hProcess);
    return 0;
}
