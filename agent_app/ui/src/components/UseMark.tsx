// The loupe's mark of whether the image is used for training (types design 17.1, user 2026-10-13): ✓ run and not
// used for training, circled ✓ used for training, ◐ running, an empty ring when nothing has run.
// Pressing switches ✓ and circled ✓ only (adopt or leave out); what to run is chosen apart.
import { Check } from "lucide-react";
import { ChooseRing } from "@/components/ChooseRing";
import { t } from "@/i18n";
import type { UseMark as Mark } from "@/lib/imageUse";

export function UseMark({
  mark,
  onToggle,
  choose,
}: {
  mark: Mark;
  onToggle: (adopt: boolean) => void;
  /** The gallery is annotating with AI: its choosing ring, not the training mark (user
   * 2026-10-14). */
  choose?: { chosen: boolean; done: boolean; label: string; onChoose: (on: boolean) => void };
}) {
  const place = "absolute left-1.5 top-1.5 z-10 grid size-6 place-items-center rounded-full";
  // Annotating with AI: the same ring as on the card, to choose the image (new or again).
  if (choose) return <ChooseRing {...choose} use={false} />;
  // Nothing annotated yet: an empty ring, so every card has its mark in the same place (user
  // 2026-10-13: "the blank one too, a circle's outline at the top left").
  if (mark === "none")
    return (
      <span
        role="img"
        aria-label={t("mark.none")}
        title={t("mark.none")}
        // Only the ring, nothing inside (user 2026-10-13: it was filled white).
        className={`${place} border-2 border-white bg-transparent shadow-[0_0_0_1px_rgb(0_0_0/0.55)]`}
      />
    );
  if (mark === "running")
    return (
      <span
        role="img"
        aria-label={t("mark.running")}
        title={t("mark.running")}
        className={`${place} bg-overlay text-heading leading-none text-processing-ink`}
      >
        ◐
      </span>
    );
  const adopted = mark === "adopted";
  return (
    <button
      type="button"
      aria-pressed={adopted}
      aria-label={t(adopted ? "mark.adopted" : "mark.ran")}
      title={t(adopted ? "mark.adopted" : "mark.ran")}
      // Pressing the mark is not a drag of the image nor a click on it.
      onPointerDown={(event) => event.stopPropagation()}
      onPointerUp={(event) => event.stopPropagation()}
      onClick={(event) => {
        event.stopPropagation();
        onToggle(!adopted);
      }}
      // As the card's ring while using for training (user 2026-10-13): green with a check when
      // used, an empty ring when not.
      className={`${place} cursor-pointer border-2 border-white shadow-[0_0_0_1px_rgb(0_0_0/0.55)] ${
        adopted ? "bg-annotated text-white" : "bg-transparent"
      }`}
    >
      {adopted && <Check className="size-4" strokeWidth={3} aria-hidden />}
    </button>
  );
}
