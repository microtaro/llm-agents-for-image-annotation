// Whether the page is the app's own window (Chrome's or Edge's --app, opened by the launcher on
// Windows with ?window=app): the launcher closes it when the app quits, so the page says nothing
// then (user 2026-10-30: "it should just go, nothing said; I pressed the power sign and then once
// more"). In a browser's tab (Mac, Linux, a tab opened by hand) it says the app stopped.
export function isAppWindow(search: string): boolean {
  return new URLSearchParams(search).get("window") === "app";
}

export const IN_APP_WINDOW =
  typeof window === "undefined" ? false : isAppWindow(window.location.search);
