// How it looks, behind an eye (user 2026-10-13: "How it looks ▾" in words read as a third thing
// to look at beside the images and the table; it is a setting, so an icon of its own kind).
// The same wherever annotations are drawn (SetEye). Opens over the page, not pushing the images down (types
// design 7.3 and 17.6: set now and then, not looked at each time).
import { Eye } from "lucide-react";
import { type ReactNode, useId } from "react";
import { DisplayControls, Slider } from "@/components/DisplayControls";
import { LabelColors } from "@/components/LabelColors";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { LIBRARY_CARD, resetLibraryLook, setDisplay, useDisplay } from "@/lib/display";
import { usePlanSeen } from "@/lib/planParts";
import { type PlanRef, planQuery } from "@/lib/route";
import { invalidate, useApi } from "@/lib/useApi";

export function LooksMenu({ children }: { children: ReactNode }) {
  return (
    <details className="relative">
      <summary
        aria-label={t("looks.open")}
        title={t("looks.open")}
        className="inline-flex size-8 cursor-pointer list-none items-center justify-center rounded-md border border-line bg-surface text-ink hover:bg-hover [&::-webkit-details-marker]:hidden"
      >
        <Eye className="size-4" aria-hidden />
      </summary>
      <div className="absolute right-0 z-30 mt-1 flex w-max max-w-[min(90vw,640px)] flex-col gap-2 rounded-md border border-line bg-sheet p-3 shadow-md">
        {children}
      </div>
    </details>
  );
}

/** The eye (definition 37.1, 37.2): one for every place that draws annotations, the same in each
 * (user 2026-10-23: every one must be the same, from a shared part): the label colors of the plan the
 * screen is judged by, read here (a label keeps its color in every plan), then how annotations
 * look, one setting for every screen. What only a place knows is
 * given: how many of each label the one image has (the loupe), the room the cards have. */
export function SetEye({
  datasetId,
  plan,
  counts,
  cardMax,
}: {
  datasetId: string;
  /** The plan the screen is judged by (none: the plan now): its labels are listed (37.3). */
  plan: PlanRef | null;
  counts?: Record<string, number>;
  cardMax?: number;
}) {
  const seen = usePlanSeen(datasetId, plan);
  const colors = useApi<{ colors: Record<string, string> }>(
    seen ? `/v1/datasets/${datasetId}/label-colors?${planQuery(seen)}` : null,
  );
  return (
    <LooksMenu>
      <LabelColors
        datasetId={datasetId}
        colors={colors.data?.colors ?? {}}
        onColors={() => invalidate(datasetId)}
        counts={counts}
      />
      <DisplayControls cardMax={cardMax} />
    </LooksMenu>
  );
}

/** The library's eye: the size of its cards only (its images have no annotations drawn), in the
 * same place and form as the images' lists (user 2026-10-29). */
export function LibraryEye() {
  const display = useDisplay();
  const own = useId();
  return (
    <LooksMenu>
      {/* The images' eye's row and its reset, the same in form (user 2026-10-29: "the others
          had a reset"). */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-body">
        <Slider
          id={`library-size-${own}`}
          label={t("display.cardSize")}
          range={LIBRARY_CARD}
          value={display.libraryCardSize}
          shown={t("display.px", { value: display.libraryCardSize })}
          onChange={(libraryCardSize) => setDisplay({ libraryCardSize })}
        />
        <Button size="small" onClick={resetLibraryLook}>
          {t("display.reset")}
        </Button>
      </div>
    </LooksMenu>
  );
}
