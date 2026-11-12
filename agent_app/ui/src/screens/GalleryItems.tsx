// The gallery's images (out of Gallery.tsx, types design 17.6): the one list of images
// (ImageSet) with what the gallery's work adds, decided here: the ring of choosing or of using for
// training, a box's targets and tags, the run going and the AI's touch.
import type { GalleryItem, StageName, View } from "@/api/types";
import { t } from "@/i18n";
import { markOf } from "@/lib/imageUse";
import { annotated, type Purpose, ringLabel } from "@/lib/selection";
import type { PlanRef } from "@/lib/route";
import { toggled } from "@/lib/viewState";
import { ImageSet, type Ring } from "./ImageSet";

export function GalleryItems({
  datasetId,
  stage,
  view,
  recordId,
  plan,
  eyePlan,
  title,
  table,
  items,
  adopting,
  colors,
  highlight,
  targets,
  tagOf,
  going,
  choosing,
  picks,
  onPicks,
  touched,
  onUsed,
  purpose = "annotate",
}: {
  datasetId: string;
  stage: StageName;
  view: View;
  recordId: string | null;
  /** The plan the cards are judged by: the loupe opened from one keeps it (definition 59.4). */
  plan: PlanRef | null;
  /** The plan of the eye's colors (a record's version when one is shown). */
  eyePlan: PlanRef | null;
  title: string;
  /** Cards or table offered (not while a box is shown). */
  table: boolean;
  items: GalleryItem[];
  /** ② over what training gets: the mark and the table's tick adopt or leave out. */
  adopting: boolean;
  colors: Record<string, string>;
  highlight: string[];
  /** The images of the box shown in the band. */
  targets: string[];
  tagOf: (imageId: string) => string | undefined;
  going: Map<string, string>;
  choosing: boolean;
  picks: string[];
  onPicks: (ids: string[]) => void;
  touched: string[];
  onUsed: (imageId: string, used: boolean) => void;
  /** ②: which decision is being made; using for training makes the ring the state itself. */
  purpose?: Purpose;
}) {
  // The ring (card) and the tick (table) are one (user 2026-10-13): choosing images (annotating
  // with AI, ① trying and references), or, while using for training, whether the image is used
  // (ticked as the rule uses it, pressed to change at once; none without an annotation).
  const using = adopting && purpose === "use";
  const ringOf = (item: GalleryItem): Ring | null => {
    if (using) {
      const mark = markOf(item);
      if (mark !== "ran" && mark !== "adopted") return null;
      return {
        on: mark === "adopted",
        label: t("image.use"),
        set: (on: boolean) => onUsed(item.image.id, on),
      };
    }
    if (!choosing) return null;
    const annotating = adopting && purpose === "annotate";
    // Annotating with AI: annotated ones show it, with the "again" button beside (user
    // 2026-10-14: the ring was empty for them, while using for training ticks what is used).
    const done = annotating && annotated(item);
    return {
      on: picks.includes(item.image.id),
      done,
      label: ringLabel(item),
      set: (on: boolean) => onPicks(toggled(picks, item.image.id, on)),
    };
  };
  return (
    <ImageSet
      datasetId={datasetId}
      items={items}
      view={view}
      colors={colors}
      plan={plan}
      eyePlan={eyePlan}
      title={title}
      stage={stage}
      recordId={recordId}
      table={table}
      picking={using || choosing ? { use: using, ringOf } : undefined}
      marks={(item) => ({
        highlighted: highlight.includes(item.image.id) || targets.includes(item.image.id),
        tag: tagOf(item.image.id),
        going: going.get(item.image.id),
        targeted: touched.includes(item.image.id),
      })}
    />
  );
}
