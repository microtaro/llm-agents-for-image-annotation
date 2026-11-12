// The gallery of one dataset's carrying out (Apply): the stage's card on top, below it the boxes
// waiting there (the decision band) and its images. The agent app (10-09): the workers and the
// talk are on the left (AgentShell). The plan's stage is its own screen (PlanInterview, definition
// 26.7); a link may name another stage, and the way back is above.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Dataset, GalleryPage, PlanState, Progress, Proposal, Run } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { PlanScreen } from "./PlanScreen";
import { GalleryItems } from "./GalleryItems";
import { workerAt } from "@/lib/home";
import { t, when } from "@/i18n";
import { listShows, useDisplay } from "@/lib/display";
import { groupOf } from "@/lib/filters";
import { attributeColumns, buildRows, findRows, type Mode } from "@/lib/table";
import { spentText, wayText, useModelName } from "@/lib/runChoice";
import { usePlanLabels, usePlanSeen } from "@/lib/planParts";
import { galleryQuery, go, type PlanRef, planOf, planQuery, viewOf } from "@/lib/route";
import { invalidate, useApi } from "@/lib/useApi";
import { GalleryHeader } from "./GalleryHeader";
import { GalleryTools } from "./GalleryTools";
import { AgentShell } from "./AgentShell";
import { useTalkTo } from "./AgentSide";
import { useBand } from "./DecisionBand";
import { GalleryBands, GalleryDecisionView } from "./GalleryDecision";
import { boxesOn, screenOfBox, targetsOf } from "@/lib/talk";
import { RunBar } from "./RunBar";
import { runGoing, useRunWatch } from "@/lib/useRunWatch";
import { RunView } from "./RunView";
import { NoPlanBand, RunDecisionBar } from "./RunDecisionBar";
import { UseBar } from "./UseBar";
import { ProductionDecisions } from "./ProductionDecisions";
import { RecordPlan } from "./RecordPlan";
import { isApplyRun, useRunDecision } from "@/lib/runDecision";
import { useSetUsed } from "@/lib/imageUse";
import { newlyWithdrawn, type PlanTarget, viewReplacesCards } from "@/lib/decisions";
import { errorText } from "@/lib/errorText";
import { runState } from "@/lib/work";
import { toast } from "sonner";
import {
  useFilter,
  usePurpose,
  useHighlight,
  useTableFind,
  useViewedBox,
  useRememberDataset,
  useDecisionShown,
  useShownOnRight,
} from "@/lib/viewState";

export function Gallery({
  datasetId,
  recordId,
  step: chosenStep = null,
  plan,
}: {
  datasetId: string;
  recordId: string | null;
  /** The step of the stage looked at (null: the one with something waiting). */
  step?: string | null;
  /** The plan its images are judged by: the one the talk is about (definition 36.1). */
  plan: PlanRef | null;
}) {
  const modelName = useModelName();
  const base = `/v1/datasets/${datasetId}`;
  const dataset = useApi<Dataset>(base);
  const runs = useApi<{ runs: Run[] }>(`${base}/runs`);
  const progress = useApi<Progress>(`${base}/progress`);
  const talking = workerAt("dataset");
  const stage = "production" as const;
  const runList = runs.data?.runs ?? [];
  // With no run chosen, ② shows what training gets and what is left to run. One run is chosen
  // in the list, to compare runs; in ① a trial's (Sol 2026-10-13: opening a trial's record went
  // back to ①'s images).
  const shownRun = recordId ? (runList.find((r) => r.id === recordId) ?? null) : null;
  const view = shownRun ? "run" : viewOf(stage);
  // ② over what training gets, by the operation's screen (user 2026-10-13, definition 34.1, 37);
  // an operation's screen shows only its things (the images it takes, its buttons, its boxes).
  const adopting = stage === "production" && !shownRun;
  const [purpose] = usePurpose(datasetId);
  // The plan the images are judged by (definition 57): using for training, the latest version
  // (what training uses, not chosen); annotating, the plan now or one chosen at the top, an
  // earlier one looked at only (a run always runs the plan now).
  const planNow = useApi<PlanState>(`${base}/plan/state`);
  const now = planNow.data ? planOf(planNow.data) : null;
  // No plan yet (no version, no draft): nothing can be annotated with AI (the server refuses it).
  const noPlan = Boolean(planNow.data) && now === null;
  const latestRevision = progress.data?.facts.revision ?? null;
  const judgedBy: PlanRef | null =
    purpose === "use" && latestRevision ? { revision: latestRevision } : plan;
  const lookingOnly = purpose === "annotate" && plan !== null && planQuery(plan) !== planQuery(now);
  const seen = usePlanSeen(datasetId, judgedBy);
  // The plan's labels: their attributes are the table's columns (definition 85).
  const labels = usePlanLabels(datasetId, seen);
  const ofPurpose = (p: Proposal) => !adopting || screenOfBox(p) === purpose;
  const versionRuns = runList.some((r) => r.of_version);
  const hasInstruction = Boolean(progress.data?.facts.revision);
  // The plan's images show the saved version's results, its trials too (Sol 2026-10-14: a
  // finished trial left its card at "-"). Annotating with AI: the newest annotation of each
  // image, not what training uses (user 2026-10-14: the other decision's state was mixed in).
  const page = useApi<GalleryPage>(
    progress.data
      ? `${base}/gallery?${galleryQuery(stage, shownRun?.id ?? null, purpose !== "use", hasInstruction, judgedBy)}`
      : null,
  );
  // A draft being made: the plan a decision opens when it names none.
  const drafting = Boolean(progress.data?.facts.instruction?.draft);
  // The filter and the table's finding are shared with the loupe and kept for the tab
  // (lib/viewState).
  const [filter, setFilter] = useFilter(datasetId, stage, shownRun?.id ?? null);
  const find = useTableFind(datasetId, stage);
  // Images the AI's answer touched: moved to and marked for a moment (step 18 design 4.1).
  const [highlight, setHighlight] = useHighlight(datasetId);
  const markUsed = useSetUsed(datasetId);
  const highlightKey = highlight.join(",");
  useEffect(() => {
    if (!highlightKey) return;
    document
      .querySelector(`[data-image="${CSS.escape(highlightKey.split(",")[0])}"]`)
      ?.scrollIntoView({ block: "center", behavior: "smooth" });
    const timer = window.setTimeout(() => setHighlight([]), 5000);
    return () => window.clearTimeout(timer);
  }, [highlightKey, setHighlight]);
  const display = useDisplay();
  // Everything of the dataset read again, in every part showing it (TanStack Query's cache;
  // found 2026-10-06: parts read apart were left old).
  const reloadAll = useCallback(() => invalidate(datasetId), [datasetId]);

  // The boxes waiting on this stage, one shown in the band; while it is shown, the view is its
  // targets ("see the others too" shows all, until another box).
  const proposals = useApi<{ proposals: Proposal[] }>(`${base}/proposals`);
  const allProposals = proposals.data?.proposals ?? [];
  const [viewed, setViewed] = useViewedBox(datasetId);
  const viewedBox = useApi<Proposal>(viewed ? `/v1/proposals/${viewed}` : null);
  useRememberDataset(datasetId);
  const talkTo = useTalkTo(datasetId);
  const [othersFor, setOthersFor] = useState<string | null>(null);

  // Others (the AI, the API) change the data too: read again on coming back to the window and
  // on choosing another stage (found 2026-10-05: a run started from the API did not show).
  const firstStage = useRef(true);
  useEffect(() => {
    if (firstStage.current) {
      firstStage.current = false;
      return;
    }
    reloadAll();
  }, [stage, reloadAll]);
  useEffect(() => {
    window.addEventListener("focus", reloadAll);
    return () => window.removeEventListener("focus", reloadAll);
  }, [reloadAll]);

  // The run going: waited for, and its images marked on the cards of the other views.
  const { active, going: goingAll } = useRunWatch(runList, reloadAll);
  const going = active && !(view === "run" && shownRun?.id === active.id) ? goingAll : new Map();

  const open = (next: typeof stage, run: string | null = null) =>
    go({ screen: "gallery", datasetId, stage: next, recordId: run });
  // A link (or a reload) with a record while using for training: over what training uses now.
  useEffect(() => {
    if (stage === "production" && purpose === "use" && recordId)
      go({ screen: "gallery", datasetId, stage, recordId: null });
  }, [stage, purpose, recordId, datasetId]);
  // The boxes waiting on this stage, one in the band (types design 17.4: the card under the map
  // replaced the steps as places; a box is of its stage, not of a step). A run is the bar's
  // (definition 40.2): its images are the rings, decided in the bar or in its line on the left.
  // Only the proposals the person asked to see here (definition 18.2): one coming by itself
  // does not change the cards (Luna 2026-10-17: the image about to be pressed went).
  const [shownRight] = useShownOnRight(datasetId);
  const bandBoxes = boxesOn(allProposals, stage)
    .filter(ofPurpose)
    .filter((p) => !isApplyRun(p) && shownRight.includes(p.id));
  // A box withdrawn (the plan written again) after the person saw it in the band is said here,
  // where it went; one never shown (while their own run was decided) is only in the worker's
  // talk (Sol 2026-10-17: the note of an unseen box covered the one of their own window).
  const seenIds = useRef<Set<string>>(new Set());
  useEffect(() => {
    const found = proposals.data?.proposals ?? [];
    for (const box of newlyWithdrawn(seenIds.current, found)) {
      seenIds.current.delete(box.id);
      // It stays where it was, as a decided box with why, until closed (Sol 2026-10-17: a note
      // that went in seconds was missed).
      setViewed(box.id);
      setPlanShown((shown) => (shown?.from === box.id ? null : shown));
    }
  }, [proposals.data, setViewed]);
  // The plan a decision runs or a record ran, opened over the page (a version, or null: the
  // plan now): the decision stays as it is (one decision at a time; the box's own view takes
  // the plan's place on the page).
  const [planShown, setPlanShown] = useState<{ target: PlanTarget; from?: string } | null>(null);
  const seePlan = (target: PlanTarget, from?: string) => setPlanShown({ target, from });
  const band = useBand(datasetId, stage, bandBoxes);
  useEffect(() => {
    if (band.box && !band.folded && band.box.waiting) seenIds.current.add(band.box.id);
  }, [band.box, band.folded]);
  const targets = band.box && band.box.waiting && !band.folded ? targetsOf(band.box) : [];
  // The box's own view (types design 16.3.1): what it makes, by its image and its data; its data
  // in place of the cards when on.
  const boxed = Boolean(band.box && !band.folded);
  const [shown, setShown] = useDecisionShown();
  const boxScreen = viewReplacesCards(boxed, shown);
  // While a box is shown, its own switches say how (one "how to show" at a time: the gallery's
  // cards-or-table and the decision's image-and-data both read "how to show: images", 10-12);
  // its image view is the cards.
  // The run where the AI works, when asked for (step=run): the one going or the last one.
  const runOfStage =
    stage === "production" && chosenStep === "run"
      ? progress.data?.facts.running?.stage === "production"
        ? active
        : (runList.find((r) => r.of_version) ?? null)
      : null;
  const runBefore = runOfStage
    ? (runList.slice(runList.indexOf(runOfStage) + 1).find((r) => r.of_version) ?? null)
    : null;
  const allItems = useMemo(() => page.data?.items ?? [], [page.data]);
  // Every image in both of ②'s decisions (user 2026-10-13: the whole dataset in view); what
  // each image takes is its ring.
  const pool = allItems;
  // A filter whose images are all gone shows all again, not an
  // empty page with no chip chosen (Astra 2026-10-07). Only with the page read, not while a
  // new one loads.
  useEffect(() => {
    if (page.data && !page.previous && filter && !pool.some((i) => groupOf(i, stage) === filter))
      setFilter(null);
  }, [page.data, page.previous, filter, pool, stage, setFilter]);
  // The rings of annotating with AI are the images of the run being decided (definition 40.2):
  // a worker's waiting run with the person's changes, else the person's own choice; a touched
  // button's targets marked on their cards.
  const decision = useRunDecision(datasetId);
  const picks = decision.images;
  const [touched, setTouched] = useState<string[]>([]);
  // A button gone with the bar (nothing chosen, another stage) leaves no card marked: its
  // mouse-leave never comes.
  useEffect(() => setTouched([]), [stage, picks.length]);
  // Choosing images (then a button): annotating with AI. Using for training has no choosing:
  // the ring is the state, pressed to change (user 2026-10-13).
  const choosing = adopting && purpose === "annotate" && !lookingOnly && !noPlan;
  // The images of the band's box (not a run's, those are the rings); the others on asking.
  const deciding = band.box?.id ?? null;
  const shownTargets = allItems.filter((i) => targets.includes(i.image.id));
  const onlyTargets = shownTargets.length > 0 && othersFor !== deciding;
  // The list puts them in the order chosen (ImageSet), as the loupe steps through them.
  const items = onlyTargets
    ? shownTargets
    : filter
      ? pool.filter((item) => groupOf(item, stage) === filter)
      : pool;
  const shows = listShows(display, !boxed, attributeColumns(items, labels).length > 0);
  // What the filter shows now, in the table its search too (Sol 2026-10-13: one row found, two
  // chosen, and no word of it): what "choose the shown" chooses.
  const searching = shows.table && !shows.cards && Boolean(find.text);
  const shownIds = searching
    ? [
        ...new Set(
          findRows(
            buildRows(items),
            find.text,
            find.mode as Mode,
            attributeColumns(items, labels),
            labels,
          ).map((r) => r.imageId),
        ),
      ]
    : items.map((i) => i.image.id);
  // What narrows what is shown, said on the bars (user 2026-10-27).
  const narrowing = { state: filter, found: searching, targets: onlyTargets };

  // The band's targets only, or all (prototype 2): in the filter's place.
  const targetChips =
    shownTargets.length > 0 ? (
      <div className="flex flex-wrap items-center gap-1.5 text-body" role="group">
        {([true, false] as const).map((only) => (
          <button
            key={String(only)}
            type="button"
            aria-pressed={onlyTargets === only}
            onClick={() => setOthersFor(only ? null : deciding)}
            className={`cursor-pointer rounded-md border px-2.5 py-0.5 ${onlyTargets === only ? (only ? "border-processing bg-processing font-semibold text-ink" : "border-ink bg-selected font-semibold text-ink") : "border-line bg-surface"}`}
          >
            {only ? t("band.targets", { count: shownTargets.length }) : t("band.others")}
          </button>
        ))}
      </div>
    ) : undefined;
  // One record looked at alone (user 2026-10-13: the "seeing" row is gone, the left says where
  // one is): chosen in ②'s "annotate with AI".
  const runPicker = versionRuns && (
    <span className="flex flex-wrap items-center gap-2">
      <span className="text-body text-muted-foreground">{t("run.choose")}</span>
      <select
        aria-label={t("run.choose")}
        // As wide as its choice shown, not its longest record (the list says each in full).
        className="max-w-[18rem] rounded-md border border-line bg-surface px-2 py-1 text-body"
        value={shownRun?.id ?? ""}
        onChange={(e) => open(stage, e.target.value || null)}
      >
        <option value="">
          {t(adopting && purpose !== "use" ? "production.newest" : "production.all")}
        </option>
        {runList.map((r) => (
          <option key={r.id} value={r.id}>
            {/* What tells records apart, as the records' table says it (definition 54: the
                dropdown is where they are compared on the screen). */}
            {[
              t("run.number", { number: r.number ?? "" }) + (r.trial ? ` · ${t("run.trial")}` : ""),
              when(r.started_at),
              wayText(r, modelName),
              `${t(`run.status.${runState(r.status, r.error_code)}`)} ${r.succeeded}/${r.total}`,
              spentText(r.elapsed_ms, r.cost?.usd),
            ]
              .filter(Boolean)
              .join(" · ")}
          </option>
        ))}
      </select>
      {/* Using a record for training is the other decision's (user 2026-10-14). */}
      {/* The record's plan and what the plan says now differently (definition 11.10). */}
      {shownRun && (
        <RecordPlan
          recordId={shownRun.id}
          runNumber={shownRun.number}
          onOpen={(revision) => seePlan({ revision })}
        />
      )}
    </span>
  );
  return (
    <AgentShell
      datasetId={datasetId}
      looking={{
        stage,
        screen: purpose,
        ...(shownRun ? { record_id: shownRun.id, record_number: shownRun.number } : {}),
        ...seen,
        // The chosen images go with the words ("annotate these" is understood).
        ...(choosing && picks.length
          ? {
              picked: allItems.filter((i) => picks.includes(i.image.id)).map((i) => i.image.name),
            }
          : {}),
      }}
      onSeePlan={seePlan}
    >
      {/* A dataset deleted (a link or a line from before): said, with the way back (Sol
        2026-10-15: an empty page named "…"). */}
      {dataset.error?.status === 404 && (
        <div className="flex flex-wrap items-center gap-3 border-b border-line bg-draft px-5 py-3 text-body">
          {t("lib.gone")}
          <Button size="small" onClick={() => go({ screen: "library" })}>
            {t("side.toLibrary")}
          </Button>
        </div>
      )}
      <div className="flex min-h-screen flex-col">
        <GalleryHeader datasetId={datasetId} dataset={dataset.data} stage={stage} plan={plan} />
        <div className="flex flex-col gap-1.5 border-b border-line bg-sheet px-5 py-2">
          {/* The thin bar, unless the run is what is shown below (the same run twice) or over
              what training gets (annotating with AI says it in its bar, definition 40.2). */}
          {active && runOfStage !== active && !adopting && (
            <RunBar run={active} onChanged={reloadAll} />
          )}
          <ProductionDecisions
            datasetId={datasetId}
            progress={progress.data}
            items={allItems}
            purpose={purpose}
            counts={page.data?.counts ?? null}
            unfilled={page.data?.unfilled ?? null}
            basis={purpose === "use" ? judgedBy : (plan ?? now)}
            plan={plan}
            // The images by another plan's results (definition 56), annotating only: training's
            // plan is the latest version (definition 57); the record looked at stays.
            onPlan={(next) =>
              go({ screen: "gallery", datasetId, stage, recordId, step: chosenStep, plan: next })
            }
            latest={
              latestRevision
                ? {
                    revision: latestRevision,
                    key: dataset.data?.requirement_key ?? null,
                    judged: page.data?.requirement_key ?? null,
                  }
                : null
            }
            lookingOnly={lookingOnly}
            onBack={() =>
              go({ screen: "gallery", datasetId, stage, recordId, step: chosenStep, plan: null })
            }
            undecided={decision.images.length > 0 && purpose === "use"}
          />
        </div>
        <div className="flex flex-1 flex-wrap items-stretch">
          <main className="flex min-w-0 flex-[999_1_560px] flex-col">
            <GalleryBands
              datasetId={datasetId}
              band={band}
              onSeePlan={seePlan}
              decided={viewedBox.data && viewed === viewedBox.data.id ? viewedBox.data : null}
              talking={talking}
              onTalk={talkTo}
              items={allItems}
            />
            <Dialog
              open={planShown !== null}
              onOpenChange={(on) => !on && setPlanShown(null)}
              title={t("work.decision.instruction")}
              wide
            >
              {planShown && (
                <PlanScreen
                  datasetId={datasetId}
                  {...(planShown.target.revision !== undefined
                    ? { version: String(planShown.target.revision) }
                    : planShown.target.write !== undefined
                      ? { write: planShown.target.write }
                      : drafting
                        ? {}
                        : { version: "latest" })}
                  images={new Map(allItems.map((i) => [i.image.id, i.image]))}
                  colors={page.data?.label_colors ?? {}}
                />
              )}
            </Dialog>
            {/* The step where the AI works: its run, in place of the stage's cards. */}
            <GalleryDecisionView
              datasetId={datasetId}
              box={band.box && !band.folded ? band.box : null}
              shown={shown}
              onShown={setShown}
              items={allItems}
              colors={page.data?.label_colors ?? {}}
              nowQuery={galleryQuery(stage, null, purpose !== "use", hasInstruction, judgedBy)}
            />
            {runOfStage && !boxScreen && (
              <RunView
                datasetId={datasetId}
                run={runOfStage}
                previous={runBefore}
                colors={page.data?.label_colors ?? {}}
              />
            )}
            <div className={runOfStage || boxScreen ? "hidden" : "contents"}>
              {page.error && <p className="px-5 text-failed">{page.error.message}</p>}
              <GalleryTools
                stage={stage}
                items={pool}
                filter={filter}
                onFilter={setFilter}
                targets={
                  <>
                    {/* Showing (step 1): a record, then the state's chips (user 2026-10-27:
                        both narrow what is shown, apart they read as two things). */}
                    {stage === "production" && purpose === "annotate" && runPicker}
                    {targetChips}
                    {/* The table's finding words are the table's: said on the cards, so images
                        do not seem to vanish between the two (Sol 2026-10-13). */}
                    {shows.cards && !shows.table && find.text && (
                      <span className="flex items-center gap-1.5 text-body text-muted-foreground">
                        {t("table.find.elsewhere", { text: find.text })}
                        <button
                          type="button"
                          className="cursor-pointer text-action underline"
                          onClick={() => find.set("", find.mode)}
                        >
                          {t("table.find.clear")}
                        </button>
                      </span>
                    )}
                  </>
                }
                targetsOnly={onlyTargets}
              />
              {/* Apply's bars: annotating decides the run of the ringed images (definition
                  40.2); using for training changes the shown images at once (user 2026-10-15). */}
              {stage === "production" && purpose === "annotate" && !shownRun && noPlan && (
                <NoPlanBand />
              )}
              {stage === "production" &&
                purpose === "annotate" &&
                !shownRun &&
                !lookingOnly &&
                !noPlan && (
                  <RunDecisionBar
                    datasetId={datasetId}
                    items={pool}
                    shown={shownIds}
                    by={narrowing}
                    going={runGoing(runList)}
                    onTargets={setTouched}
                    onSeePlan={seePlan}
                  />
                )}
              {stage === "production" && purpose === "use" && (
                <UseBar datasetId={datasetId} items={pool} shown={shownIds} by={narrowing} />
              )}
              {/* The images, as every list of images (ImageSet: its head row, the order, cards or
                  table and the eye), with the gallery's rings and marks. */}
              <div className="px-5 py-3">
                <GalleryItems
                  purpose={purpose}
                  datasetId={datasetId}
                  stage={stage}
                  view={view}
                  recordId={shownRun?.id ?? null}
                  plan={judgedBy}
                  // A record's version; a trial of a draft has none (planOf: revision 0 is no plan).
                  eyePlan={
                    shownRun ? planOf({ revision: shownRun.instruction_revision }) : judgedBy
                  }
                  title={t("gallery.list", { count: items.length })}
                  // A box shown has its own switches (one "how to show" at a time).
                  table={!boxed}
                  items={items}
                  adopting={adopting}
                  colors={page.data?.label_colors ?? {}}
                  highlight={highlight}
                  targets={targets}
                  tagOf={(imageId) =>
                    band.box && targets.includes(imageId)
                      ? t(`band.tag.${band.box.tool}`)
                      : undefined
                  }
                  going={going}
                  choosing={choosing}
                  picks={picks}
                  onPicks={decision.setImages}
                  touched={touched}
                  onUsed={(imageId, on) =>
                    // Taken back from the notice, as everywhere a change is made at once (user
                    // 2026-10-14: annotating had "undo", using for training did not).
                    void markUsed(imageId, on)
                      .then(() =>
                        toast.success(
                          t(on ? "select.use.done" : "select.unuse.done", { count: 1 }),
                          {
                            action: {
                              label: t("select.undo"),
                              onClick: () =>
                                void markUsed(imageId, !on).catch((reason) =>
                                  toast.error(errorText(reason)),
                                ),
                            },
                          },
                        ),
                      )
                      .catch((reason) => toast.error(errorText(reason)))
                  }
                />
              </div>
            </div>
          </main>
        </div>
      </div>
    </AgentShell>
  );
}
