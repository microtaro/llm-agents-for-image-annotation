// One bar of the images by state and its one number; the parts in words on hover (definition 57).
import type { StateCounts } from "@/api/types";
import { type BarKind, barNumber, barParts, barWords } from "@/lib/stateCounts";

const FILL = {
  annotated: "bg-annotated",
  processing: "bg-processing",
  failed: "bg-failed",
  unprocessed: "bg-unprocessed",
} as const;

export function StateBar({
  counts,
  kind,
  hint,
}: {
  counts: StateCounts;
  kind: BarKind;
  /** How the screen's images are worked, said on hover after the parts (not a line of its own). */
  hint?: string;
}) {
  const total = counts.images || 1;
  return (
    <span
      className="flex min-w-0 flex-[1_1_320px] items-center gap-2.5"
      title={[barWords(counts, kind), hint].filter(Boolean).join("\n")}
    >
      <span className="flex h-2.5 min-w-24 flex-1 overflow-hidden rounded-full bg-track">
        {barParts(counts, kind)
          .filter((p) => p.count)
          .map((p) => (
            <span
              key={p.key}
              className={`block h-full ${FILL[p.color]}`}
              style={{ width: `${(100 * p.count) / total}%` }}
            />
          ))}
      </span>
      <span className="shrink-0 font-semibold tabular-nums">{barNumber(counts, kind)}</span>
    </span>
  );
}
