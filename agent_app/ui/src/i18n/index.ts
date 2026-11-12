// Every word a person reads lives in ja.json and en.json only (AGENTS.md). t(key, {name})
// looks it up in the chosen language; the choice stays in this browser.
import { useSyncExternalStore } from "react";
import en from "./en.json";
import ja from "./ja.json";

export type Lang = "ja" | "en";
const DICTS: Record<Lang, Record<string, string>> = { ja, en };
const KEY = "agent-app.lang";

/** The language a screen starts in: the one chosen in this browser, else the browser's own
 * (2026-11-09: it was always Japanese, so readers of the English page met a Japanese screen). */
export function startLang(saved: string | null, browser: string): Lang {
  if (saved === "ja" || saved === "en") return saved;
  return browser.toLowerCase().startsWith("ja") ? "ja" : "en";
}

function initial(): Lang {
  let saved: string | null = null;
  try {
    saved = window.localStorage.getItem(KEY);
  } catch {
    // Storage may be blocked; the browser's language decides.
  }
  return startLang(saved, window.navigator.language ?? "");
}

let lang: Lang = typeof window === "undefined" ? "ja" : initial();
const listeners = new Set<() => void>();

export function t(key: string, vars: Record<string, string | number> = {}): string {
  return fill(DICTS[lang][key] ?? key, vars, lang);
}

/** The words with their values: {name} is the value, {name|one|other} the words for its number
 * in the language (2026-10-30: English said "1 images"; Japanese has one form). */
export function fill(text: string, vars: Record<string, string | number>, language: Lang): string {
  const rules = new Intl.PluralRules(language);
  return text
    .replace(
      /\{(\w+)\|([^|{}]*)\|([^|{}]*)\}/g,
      (whole, name: string, one: string, other: string) =>
        name in vars ? (rules.select(Number(vars[name])) === "one" ? one : other) : whole,
    )
    .replace(/\{(\w+)\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole));
}

/** Whether the dictionary has a word for the key (for words picked by an error code). */
export function has(key: string): boolean {
  return key in DICTS[lang];
}

export function setLang(next: Lang) {
  lang = next;
  try {
    window.localStorage.setItem(KEY, next);
  } catch {
    // Not remembered; the choice still holds for this page.
  }
  document.documentElement.lang = next;
  listeners.forEach((listener) => listener());
}

/** The language chosen now (sent with every request: the workers answer in it). */
export function currentLang(): Lang {
  return lang;
}

export function useLang(): Lang {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => lang,
  );
}

/** Dates and times in the chosen language, shown in the viewer's time zone (JST here). */
export function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(lang === "ja" ? "ja-JP" : "en-US", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
