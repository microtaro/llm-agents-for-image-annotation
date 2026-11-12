// The size of the text (user 2026-10-14: "my eyes are weak, others differ"): the body's size,
// 13px at the standard, chosen in the settings and kept in this browser like the theme. Every
// step of the text (index.css --text-*) is in rem, so the root's size moves them together;
// the labels drawn on images keep their own size (the display row).
import { useSyncExternalStore } from "react";

const KEY = "agent-app.text-size";
export const STANDARD = 13;
export const SIZES = [11, 12, 13, 14, 15, 16];
const listeners = new Set<() => void>();

export function currentTextSize(): number {
  try {
    const value = Number(window.localStorage.getItem(KEY));
    return SIZES.includes(value) ? value : STANDARD;
  } catch {
    return STANDARD;
  }
}

/** The root's size for a body of this size (14px at the standard 13px). */
export function rootSize(body: number): number {
  return (body * 14) / STANDARD;
}

export function applyTextSize(body: number = currentTextSize()): void {
  document.documentElement.style.fontSize = `${rootSize(body)}px`;
}

export function setTextSize(body: number): void {
  try {
    window.localStorage.setItem(KEY, String(body));
  } catch {
    // Without storage it lasts while the page is open.
  }
  applyTextSize(body);
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTextSize(): number {
  return useSyncExternalStore(subscribe, currentTextSize);
}
