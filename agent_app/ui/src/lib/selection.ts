// Choose images first, then press a named button (types design 17.4, user 2026-10-13; as mail
// and photo apps do). Each button says how many of the chosen images it works on, and touching
// it marks those cards; this file decides which they are, apart from the screen.
import type { GalleryItem } from "@/api/types";
import { t } from "@/i18n";
import { markOf } from "./imageUse";

/** What the images are chosen for in ② (user 2026-10-13, as annotation tools split labeling
 * from review): annotating (every image, done ones too, to do again) or choosing what training
 * uses (only the annotated ones). */
/** The screen of ②'s right (definition 34.1, 37): annotating with AI (its run before and while it
 * goes) and using for training. */
export type Purpose = "annotate" | "use";

/** An image with an annotation that training can use (run, or used now). */
export function annotated(item: GalleryItem): boolean {
  const mark = markOf(item);
  return mark === "ran" || mark === "adopted";
}

/** A choosing ring's words while annotating with AI: an annotated image is chosen to do again,
 * said made by other criteria when it is (definition 85.4). */
export function ringLabel(item: GalleryItem): string {
  const name = item.image.name;
  if (!annotated(item)) return t("select.one", { name });
  return t(item.badge.other ? "select.again.other" : "select.again", { name });
}

/** What annotating the chosen images with AI would be (user 2026-10-14): new ones, and ones
 * done again. What a success changes for training is the run's card (the server's, definition
 * 19.6: a person's choice stays). */
export function runSplit(items: GalleryItem[], chosen: string[]) {
  const mine = items.filter((i) => chosen.includes(i.image.id));
  const again = mine.filter(annotated);
  return { fresh: mine.length - again.length, again: again.length };
}

/** Of all the images, after the bar's button (user 2026-10-16: the total is what one wants to
 * know, not how many a press moves): done by the plan, expected once the chosen ones are done
 * (an annotation made by other criteria is done only when made again or checked,
 * definition 85.4). */
export function annotatedAfter(items: GalleryItem[], chosen: string[]): number {
  return items.filter((i) => (annotated(i) && !i.badge.other) || chosen.includes(i.image.id))
    .length;
}

/** Of all the images, used for training once the given ones are used (on) or left out. */
export function usedAfter(items: GalleryItem[], ids: string[], on: boolean): number {
  const used = items.filter((i) => markOf(i) === "adopted").length;
  return used + (on ? ids.length : -ids.length);
}

/** A run's cost limit per image and of all its images, in dollars to two places (definition
 * 65, user 2026-10-28: each card says one image's cost, so the limit is per image and said in
 * all too). */
export function budgetWords(perImage: unknown, images: number): { budget: string; total: string } {
  const value = Number(perImage);
  if (perImage === null || perImage === undefined || perImage === "" || !Number.isFinite(value))
    return { budget: "—", total: "—" };
  return { budget: value.toFixed(2), total: (value * images).toFixed(2) };
}

/** What narrows what is shown (user 2026-10-27: the bars say which images they work on, by what
 * narrows them): a state's chip, a search, a box's images only. */
export interface Narrowing {
  state?: string | null;
  found?: boolean;
  targets?: boolean;
}

/** Which of them the bars work on, in words ("all 50", "the 46 with no result yet"): all of
 * them; by the one thing that narrows them; "the shown" when more than one does or a box's
 * images are shown. */
export function shownWhich(count: number, by: Narrowing, datasets = false): string {
  if (datasets)
    return t(by.found ? "select.which.datasets.found" : "select.which.datasets.whole", { count });
  const ways = [Boolean(by.state), Boolean(by.found), Boolean(by.targets)];
  if (ways.filter(Boolean).length > 1 || by.targets) return t("select.which.shown", { count });
  if (by.state) return t("select.which.state", { count, name: t(`filter.${by.state}`) });
  if (by.found) return t("select.which.found", { count });
  return t("select.which.whole", { count });
}
