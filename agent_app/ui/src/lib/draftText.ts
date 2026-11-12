// The words of how an instruction changed (step 19): the server's difference of two contents
// (a draft against the version, or against the draft before an answer), and the text cut into
// sentences the way the server cuts it, so the changed ones can be marked in the whole text.
import { planPartItems } from "./decisions";

export interface DraftDiff {
  /** Against a version: its number (null: no version yet). Absent against a draft. */
  revision?: number | null;
  added: string[];
  removed: string[];
  /** A label of the library renamed: [its name before, its name now]. */
  renamed: [string, string][];
  changed: string[];
  /** Labels whose description (or an attribute's) changed. */
  described: string[];
  text_changed: boolean;
  references: [number, number];
  text: { added: string[]; removed: string[]; more: number };
  leave_out: { added: string[]; removed: string[]; more: number };
}

/** Nothing differs. */
export function same(diff: DraftDiff): boolean {
  return !planPartItems(diff).length && !diff.text.added.length && !diff.text.removed.length;
}

/** How a label of the plan differs from the one compared with, for its mark; null: the same. */
export function labelMark(
  diff: DraftDiff | null | undefined,
  name: string,
): "added" | "renamed" | "changed" | "described" | null {
  if (!diff) return null;
  if (diff.added.includes(name)) return "added";
  if (diff.renamed.some(([, now]) => now === name)) return "renamed";
  if (diff.changed.includes(name)) return "changed";
  if (diff.described.includes(name)) return "described";
  return null;
}

/** Each line of the text cut after the full stop (Japanese or not), "!" or "?" (as the server's draft_diff does),
 * with the pieces kept whole so the line reads the same. */
export function sentencesOf(text: string): string[][] {
  return text
    .split("\n")
    .map((line) =>
      line.split(/(?<=[\u3002.!?\uff01\uff1f])/).filter((piece) => piece.trim() !== ""),
    );
}
