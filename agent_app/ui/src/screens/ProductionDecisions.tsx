// ② carrying out's top (definition 34.1, 35.3; user 2026-10-22: the right is for seeing how the
// annotation goes and what is going on): what the plan the screen judges by puts on the images and
// one bar for the screen's question (definition 57: annotating, how far the annotation came by the
// plan a run uses; training, what training uses by the latest version); the screen chosen at the
// top (annotating with AI, using for training) shows only its parts below. The record to look at
// is chosen in the filter row (user 2026-10-27). A decision is made on the left as well; either
// way both show it.
import type { GalleryItem, ObjectType, Progress, Shown, StateCounts } from "@/api/types";
import { StateBar } from "@/components/StateBar";
import { t } from "@/i18n";
import { basisWords, usePlanLabels } from "@/lib/planParts";
import { go, type PlanRef } from "@/lib/route";
import { annotated, type Purpose } from "@/lib/selection";
import { labelsFull, labelsLine, unfilledLine } from "@/lib/stateCounts";
import { Button } from "@/components/ui/button";
import { PlanBasis } from "./PlanBasis";

export function ProductionDecisions({
  datasetId,
  progress,
  items,
  purpose,
  counts,
  unfilled,
  basis,
  latest,
  lookingOnly,
  onBack,
  undecided = false,
  plan,
  onPlan,
}: {
  datasetId: string;
  progress: Progress | null;
  items: GalleryItem[];
  purpose: Purpose;
  /** The images in each state by the plan the screen judges by (the gallery's). */
  counts: StateCounts | null;
  /** For each attribute of that plan, the images it is not filled in (the gallery's, 85.17). */
  unfilled: Record<string, number> | null;
  /** That plan: the plan now or one chosen while annotating, the latest version for training. */
  basis: PlanRef | null;
  /** The latest version and its requirement, what training uses. */
  latest: { revision: number; key: string | null; judged: string | null } | null;
  /** An earlier plan chosen at the top: looked at only (definition 57). */
  lookingOnly: boolean;
  onBack: () => void;
  /** A run the person opened and has not decided, kept on annotating's screen. */
  undecided?: boolean;
  /** The plan the talk judges by and another chosen to look by, annotating only: chosen at the
   * head of this row (user 2026-10-28: out of the top row, beside what it puts on). */
  plan: PlanRef | null;
  onPlan: (plan: PlanRef | null) => void;
}) {
  const labels = usePlanLabels(datasetId, basis);
  const going = progress?.facts.running ?? null;
  const see = (type: ObjectType, where: Shown["where"], title: string) =>
    go({ screen: "objects", datasetId, type, where, id: null, title });
  const count = (filter: (i: GalleryItem) => boolean) => items.filter(filter).length;
  // A draft putting on other things than the latest version: a run saves it as the next version,
  // and training then uses that version's results (said before deciding, as a fact).
  const draft = Boolean(basis && "write" in basis);
  const changed =
    purpose === "annotate" && draft && latest && latest.judged && latest.judged !== latest.key;
  // Annotating chooses the plan at the head of the row, which names it; training's plan, the
  // latest version, is said there (user 2026-10-28: the labels say what information comes).
  const choosing = purpose === "annotate";
  const put = purpose === "use" && basis ? basisWords(basis) : null;
  const chooser = choosing ? <PlanBasis datasetId={datasetId} plan={plan} onPlan={onPlan} /> : null;

  return (
    <section aria-label={t(`apply.screen.${purpose}`)} className="flex flex-col gap-2 text-body">
      {lookingOnly && basis ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {chooser}
          <b>{t("look.only", { plan: basisWords(basis) })}</b>
          <Button size="small" variant="link" onClick={onBack}>
            {t("look.back")}
          </Button>
        </div>
      ) : (
        <>
          {/* The plan, what it puts on and the screen's bar in one row, wrapping when narrow. */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            {chooser}
            {labels && labels.length > 0 && (
              <span className="flex min-w-0 items-baseline gap-2" title={labelsFull(labels)}>
                {put && <b className="shrink-0">{put}</b>}
                <span className="min-w-0 truncate text-muted-foreground">{labelsLine(labels)}</span>
              </span>
            )}
            {counts && (
              <StateBar
                counts={counts}
                kind={purpose === "use" ? "training" : "annotation"}
                // How training's rings work, on hover (user 2026-10-28: not a line of its own).
                hint={
                  purpose === "use" ? t("decide.use.how", { count: count(annotated) }) : undefined
                }
              />
            )}
            {purpose === "annotate" && unfilledLine(unfilled) && (
              <span className="text-muted-foreground tabular-nums">{unfilledLine(unfilled)}</span>
            )}
            {going && purpose === "annotate" && (
              <span className="text-muted-foreground tabular-nums">
                {t("card.run.going", { done: going.done, total: going.total })}
              </span>
            )}
            {undecided && (
              <span className="rounded-full bg-action px-2 text-small font-semibold text-white">
                {t("decide.undecided")}
              </span>
            )}
          </div>
          {changed && latest && (
            <p className="m-0">
              {t("put.changed", {
                revision: latest.revision,
                next: latest.revision + 1,
                used: progress?.facts.counts?.used ?? 0,
              })}
            </p>
          )}
        </>
      )}
      {purpose === "use" ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 empty:hidden">
          {(
            [
              ["human", (i: GalleryItem) => i.badge.by === "human", { result: "human" }],
              ["newer", (i: GalleryItem) => Boolean(i.badge.newer), { newer: true }],
              ["excluded", (i: GalleryItem) => i.image.excluded, { excluded: true }],
            ] as const
          ).map(([key, filter, where]) =>
            count(filter) ? (
              <Button
                key={key}
                size="small"
                variant="link"
                onClick={() => see("image", where, t(`filter.${key}`))}
              >
                {t(`card.${key}`, { count: count(filter) })}
              </Button>
            ) : null,
          )}
        </div>
      ) : null}
    </section>
  );
}
