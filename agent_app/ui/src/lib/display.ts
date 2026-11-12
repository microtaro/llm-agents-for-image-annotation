// How annotations are shown to people (DESIGN.md 5): the same line width in the gallery and
// the loupe, card size, label tags, showing annotations at all. Kept in this browser only;
// saved annotations never change. Ranges are the current screen's (annotation_server).
import { useSyncExternalStore } from "react";

export const LINE = { min: 0.5, max: 12, step: 0.5, initial: 2 };
export const TAG = { min: 8, max: 20, step: 1, initial: 11 };
export const CARD = { min: 120, max: 1600, step: 10, initial: 220, ratio: true };
/** The library's cards, apart from the images' (user 2026-10-29: two across only; at times
 * datasets are chosen by their images alone, six or eight across). Below COMPACT a card shows
 * its images and name only, the rest on hover. */
export const LIBRARY_CARD = { min: 150, max: 640, step: 10, initial: 400, ratio: true };
export const LIBRARY_COMPACT = 300;

/** The card size's slider is even in ratio, as the current screen's (`zoomFromSlider`): each
 * step makes the cards the same share bigger, so the sizes used get most of its length (user
 * 2026-10-07: on an even slider the big sizes, of no use, took most of it). */
export const RATIO_STEPS = 100;

export function ratioStep(value: number, range: { min: number; max: number }): number {
  return Math.round((RATIO_STEPS * Math.log(value / range.min)) / Math.log(range.max / range.min));
}

export function valueAt(place: number, range: { min: number; max: number; step: number }) {
  const value = range.min * (range.max / range.min) ** (place / RATIO_STEPS);
  return Math.min(range.max, Math.max(range.min, Math.round(value / range.step) * range.step));
}

/** Labels in one order everywhere: the colors, the counts, the table and the lists of objects
 * (Astra 2026-10-07: the colors went by when each label got its color, the table by name). */
export const byLabel = (a: string, b: string) => a.localeCompare(b);

/** "box 2 · circle 3": how many objects of each label, in the labels' order. */
export function labelCounts(annotations: { label: string }[]): string {
  const by: Record<string, number> = {};
  for (const a of annotations) by[a.label] = (by[a.label] ?? 0) + 1;
  return Object.keys(by)
    .sort(byLabel)
    .map((label) => `${label} ${by[label]}`)
    .join(" · ");
}

/** The tag's text on its label color: whichever of dark and white reads better, by the WCAG
 * contrast ratio (Astra 2026-10-06: white on yellow #ffe119 or cyan #42d4f4 could not be read;
 * Sol 2026-10-12: white on orange #f58231 was 2.6:1 under the old brightness line). */
export function inkOn(color: string): string {
  const hex = /^#([0-9a-f]{6})$/i.exec(color)?.[1];
  if (!hex) return "#ffffff";
  const linear = (at: number) => {
    const c = parseInt(hex.slice(at, at + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const lum = 0.2126 * linear(0) + 0.7152 * linear(2) + 0.0722 * linear(4);
  const DARK = 0.0129; // #1b1f24
  return (lum + 0.05) / (DARK + 0.05) > 1.05 / (lum + 0.05) ? "#1b1f24" : "#ffffff";
}

export interface Display {
  overlay: boolean;
  tags: boolean;
  tagSize: number;
  lineWidth: number;
  cardSize: number;
  libraryCardSize: number;
  /** The gallery's cards and its table (one row per object), either or both, as a decision's
   * image and data (user 2026-10-13: here only one could be on). The table is null until the
   * person turns it on or off: then it is on where the results shown read values (user
   * 2026-10-29: "a table with values not on reads as none"; turning it off by hand is kept). */
  cards: boolean;
  table: boolean | null;
  /** Goes up on every reset, so each card's own zoom starts over too. */
  epoch: number;
}

/** The table on: as the person chose, else where the results shown read values (their columns,
 * lib/table.attributeColumns). */
export function tableOn(display: Pick<Display, "table">, valuesShown: boolean): boolean {
  return display.table ?? valuesShown;
}

/** What a list of images shows: the table when it is offered and on, the cards when it is on or
 * the table is not offered (a box shown has its own switches; the gallery shows cards then). */
export function listShows(
  display: Pick<Display, "cards" | "table">,
  tableOffered: boolean,
  valuesShown: boolean,
) {
  const table = tableOffered && tableOn(display, valuesShown);
  return { table, cards: display.cards || !table };
}

export const INITIAL: Display = {
  overlay: true,
  tags: true,
  tagSize: TAG.initial,
  lineWidth: LINE.initial,
  cardSize: CARD.initial,
  libraryCardSize: LIBRARY_CARD.initial,
  cards: true,
  table: null,
  epoch: 0,
};
// .2 (2026-10-29): before, every saved setting held table false though nobody chose it.
const KEY = "agent-app.display.2";

const withinRange = (value: unknown, range: { min: number; max: number; initial: number }) => {
  const number = Number(value);
  return Number.isFinite(number) ? Math.min(range.max, Math.max(range.min, number)) : range.initial;
};

/** A saved setting read back: unknown fields dropped, numbers kept inside their ranges. */
export function readDisplay(saved: unknown): Display {
  const raw = (saved && typeof saved === "object" ? saved : {}) as Partial<Display>;
  return {
    overlay: raw.overlay !== false,
    tags: raw.tags !== false,
    tagSize: withinRange(raw.tagSize, TAG),
    lineWidth: withinRange(raw.lineWidth, LINE),
    cardSize: withinRange(raw.cardSize, CARD),
    libraryCardSize: withinRange(raw.libraryCardSize, LIBRARY_CARD),
    // At least one shown.
    cards: raw.cards !== false || raw.table !== true,
    table: typeof raw.table === "boolean" ? raw.table : null,
    epoch: 0,
  };
}

function load(): Display {
  try {
    return readDisplay(JSON.parse(window.localStorage.getItem(KEY) ?? "{}"));
  } catch {
    return INITIAL;
  }
}

let current: Display = typeof window === "undefined" ? INITIAL : load();
const listeners = new Set<() => void>();

export function setDisplay(change: Partial<Display>) {
  current = { ...current, ...change };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // Not remembered; still applied on this page.
  }
  listeners.forEach((listener) => listener());
}

export function resetDisplay() {
  // The look only: cards or table is what is being worked in, kept (Astra 2026-10-07: a
  // reset in the loupe went back to the cards, so the table's search no longer applied); the
  // library's size is the library's own reset's.
  setDisplay({
    ...INITIAL,
    cards: current.cards,
    table: current.table,
    libraryCardSize: current.libraryCardSize,
    epoch: current.epoch + 1,
  });
}

/** The library's eye's reset: its size only. */
export function resetLibraryLook() {
  setDisplay({ libraryCardSize: LIBRARY_CARD.initial });
}

export function useDisplay(): Display {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
  );
}
