// Light or dark (2026-10-07, user: switched at the top right). Chosen once, kept in this
// browser; before a choice, the system's. The page reads it as <html data-theme="dark">
// (index.css holds both sets of colors).
import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";
const KEY = "agent-app.theme";
const listeners = new Set<() => void>();

function stored(): Theme | null {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

function system(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function currentTheme(): Theme {
  return stored() ?? system();
}

/** The page's colors follow the theme. */
export function applyTheme(theme: Theme = currentTheme()): void {
  document.documentElement.dataset.theme = theme;
}

export function setTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(KEY, theme);
  } catch {
    // Without storage it lasts while the page is open.
  }
  applyTheme(theme);
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, currentTheme);
}
