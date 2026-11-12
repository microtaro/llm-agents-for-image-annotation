// The ring at an image's top left that chooses it (user 2026-10-13), on its card and in the
// loupe alike (user 2026-10-14: the loupe showed the training mark while annotating).
import { Check, RotateCw } from "lucide-react";

/** Choosing an image (user 2026-10-13): a ring at the top left, empty inside, every image
 * unchosen at first; pressed, a check fills it. What the chosen ones are for is the selection
 * bar's buttons. Pressing it is not a drag of the image nor a click that opens the loupe. */
export function ChooseRing({
  chosen,
  label,
  use,
  done,
  onChoose,
  inline = false,
}: {
  chosen: boolean;
  label: string;
  /** Used for training (user 2026-10-13: green, as its pill, so a ticked one reads as "used",
   * not as chosen). */
  use: boolean;
  /** Already annotated, while annotating with AI: choosing it is doing it again, so the ring
   * is the "again" arrow (user 2026-10-14). */
  done: boolean;
  onChoose: (on: boolean) => void;
  /** In a table's row, not over an image. */
  inline?: boolean;
}) {
  const ring = (
    <button
      type="button"
      role="checkbox"
      aria-checked={chosen}
      aria-label={label}
      title={label}
      onPointerDown={(event) => event.stopPropagation()}
      onPointerUp={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        onChoose(!chosen);
      }}
      // Over an image, seen on light and dark ones alike: a white ring with a dark edge. In a
      // table's row, on the sheet: one ink edge, the fill's colour when chosen (user 2026-10-16:
      // the white edge vanished on the sheet, so the empty and the used ring looked different).
      className={`grid size-6 shrink-0 cursor-pointer place-items-center rounded-full border-2 ${
        inline
          ? chosen
            ? use
              ? "border-annotated"
              : "border-action"
            : "border-ink"
          : "border-white shadow-[0_0_0_1px_rgb(0_0_0/0.55)]"
      } ${
        chosen
          ? `text-white ${use ? "bg-annotated" : "bg-action"}`
          : done
            ? `${inline ? "bg-transparent" : "bg-overlay"} text-ink`
            : "bg-transparent"
      }`}
    >
      {done ? (
        <RotateCw className="size-3.5" strokeWidth={2.5} aria-hidden />
      ) : (
        chosen && <Check className="size-4" strokeWidth={3} aria-hidden />
      )}
    </button>
  );
  // Only what can be pressed (user 2026-10-14: a check beside the arrow read as pressable too);
  // that it is annotated is the arrow's shape and the pill below.
  return inline ? ring : <div className="absolute top-1.5 left-1.5 z-10">{ring}</div>;
}
