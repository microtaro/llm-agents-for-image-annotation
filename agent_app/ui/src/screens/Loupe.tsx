// The loupe: one image large, looking at what the gallery was looking at (step 6 design 2), and
// fixing its result on the same image when it has one (types design 7; user 2026-10-27: a second
// screen to fix lost the zoom). The agent app (10-09): the workers and the talk stay on the
// left, and the image looked at goes with the words.
import { SettingsButton } from "@/components/SettingsButton";
import { ThemeToggle } from "@/components/ThemeToggle";
import { type ReactNode, useEffect, useRef, useState } from "react";
import type {
  GalleryItem,
  Dataset,
  GalleryPage,
  LabelDefinition,
  Progress,
  Proposal,
  StageName,
  View,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { workerAt } from "@/lib/home";
import { t, when } from "@/i18n";
import { SetEye } from "@/components/LooksMenu";
import { tableOn, useDisplay } from "@/lib/display";
import { usePlanLabels, usePlanSeen } from "@/lib/planParts";
import { closeLoupe, galleryQuery, go, goReplacing, type PlanRef, viewOf } from "@/lib/route";
import { modelLabel, versionOf, useModelName } from "@/lib/runChoice";
import { shownImages } from "@/lib/shown";
import { useApi } from "@/lib/useApi";
import { isApplyRun, useRunDecision } from "@/lib/runDecision";
import { toggled, usePurpose } from "@/lib/viewState";
import { annotated, ringLabel } from "@/lib/selection";
import { markOf, type UseMark as UseMarkKind, useSetUsed } from "@/lib/imageUse";
import { toast } from "sonner";
import { api } from "@/api/client";
import {
  useFilter,
  useImageOrder,
  useLastObject,
  useTableFind,
  useRememberDataset,
  useShownOnRight,
  useViewedBox,
} from "@/lib/viewState";
import { LoupeActions } from "./LoupeActions";
import { focusImageNext } from "@/lib/focusBack";
import { ResultEditor } from "./ResultEditor";
import { UseMark } from "@/components/UseMark";
import { invalidate } from "@/lib/useApi";
import { LoupeSide, type ResultRef } from "./LoupeSide";
import { type LoupeMark, LoupeView } from "./LoupeView";
import { AgentShell } from "./AgentShell";
import { boxesAbout, DecidedBand, DecisionBand, useBand } from "./DecisionBand";
import { useTalkTo } from "./AgentSide";
import { JobsButton } from "./WorkJobs";
import { errorText } from "@/lib/errorText";
import { attributeColumns, hasAnswer } from "@/lib/table";

export function Loupe({
  datasetId,
  imageId,
  stage,
  recordId,
  objectId = null,
  plan,
}: {
  datasetId: string;
  imageId: string;
  stage: StageName;
  recordId: string | null;
  /** Shown selected (opened from a row of the table). */
  objectId?: string | null;
  /** The plan the image is judged by (definition 36.1). */
  plan: PlanRef | null;
}) {
  const modelName = useModelName();
  const base = `/v1/datasets/${datasetId}`;
  useRememberDataset(datasetId);
  const view: View = viewOf(stage);
  const [purpose] = usePurpose(datasetId);
  // Annotating with AI: the newest annotation, as on the cards, not what
  // training uses (user 2026-10-14, definition 34.1). A record opened from the list stays so
  // (user 2026-10-14: opened, it said "used for training").
  const annotating = stage === "production" && purpose !== "use";
  // A record looked at while using for training: its own mark on the image (user 2026-10-16:
  // choosing a record showed no mark, so whether it was used could not be seen there).
  const records = useApi<{ results: ResultRef[] }>(
    stage === "production" && !annotating && recordId
      ? `/v1/datasets/${datasetId}/images/${imageId}/results`
      : null,
  );
  const seen = usePlanSeen(datasetId, plan);
  // The plan's labels: their attributes are the table's columns (definition 85).
  const labels = usePlanLabels(datasetId, seen);
  const shownRecord = recordId
    ? records.data?.results.find((r) => r.run_id === recordId)
    : undefined;
  // The same cards as the gallery's, by the same query (definition 14).
  const progress = useApi<Progress>(`${base}/progress`);
  const page = useApi<GalleryPage>(
    progress.data
      ? `${base}/gallery?${galleryQuery(stage, recordId, annotating, Boolean(progress.data.facts.revision), plan)}`
      : null,
  );
  // Whose image and which run, named in the top rows as in the gallery.
  const dataset = useApi<Dataset>(base);
  const { reload } = page;
  // A person's fix of the result (types design 7.1): the plan's labels, and whether something
  // was changed (the top row says it is being fixed).
  const [changed, setChanged] = useState(false);
  useEffect(() => setChanged(false), [imageId]);
  const instruction = useApi<{ label_definitions: LabelDefinition[] }>(
    stage === "instruction" ? null : `${base}/instructions/latest`,
  );
  const all = page.data?.items ?? [];
  // The same images as the gallery's screen, in its order, so "next" stays in the filter and
  // the table's finding; the image opened outside them steps through all (lib/shown).
  const [filter] = useFilter(datasetId, stage, recordId);
  // The ring is the image's place in the run being decided, as on its card (definition 40.2).
  const decision = useRunDecision(datasetId);
  const picks = decision.images;
  const find = useTableFind(datasetId, stage);
  const display = useDisplay();
  const [imageOrder] = useImageOrder(datasetId);
  const order = shownImages(
    all,
    stage,
    filter,
    tableOn(display, attributeColumns(all, labels).length > 0) ? find : null,
    imageOrder,
    labels,
  );
  const byId = new Map(all.map((i) => [i.image.id, i]));
  // An image that has just left the filter stays among the filter's images in its place, so
  // "next" goes on to the next one (Astra 2026-10-07: 1/2 became 3/8). With none of the filter
  // left, all the images.
  const kept = new Set([...order, imageId]);
  const items = order.includes(imageId)
    ? order.flatMap((id) => byId.get(id) ?? [])
    : order.length
      ? all.filter((i) => kept.has(i.image.id))
      : all;
  const index = items.findIndex((item) => item.image.id === imageId);
  const item = index >= 0 ? items[index] : null;
  // A successful result shown, in ② (① shows the images): a person fixes it or chooses it as the
  // image's reference.
  const answer =
    stage !== "instruction" && item?.badge.result_id && hasAnswer(item.badge)
      ? item.badge.result_id
      : null;
  // Fixed on the image itself; a result with masks is only looked at (they cannot be fixed yet).
  const fixable = Boolean(answer) && !item?.annotations.some((a) => a.geometry.type === "mask");
  // The record looked at (a run or a person's fix, definition 21.4): the chosen one, or the one
  // this image's card shows, as its badge says it.
  const seenRecord = view === "run" && item?.badge.record_at ? item.badge : null;
  const markUsed = useSetUsed(datasetId);
  const [lastObject, setLastObject] = useLastObject(datasetId);
  useEffect(() => {
    if (objectId && objectId !== lastObject) setLastObject(objectId);
  }, [objectId, lastObject, setLastObject]);
  // The top row's height, so the right panel stays in view below it and scrolls by itself
  // (--loupe-head; Astra 2026-10-06: a long list pushed the image out of view).
  const head = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = head.current;
    if (!element) return;
    const observer = new ResizeObserver(() =>
      document.documentElement.style.setProperty("--loupe-head", `${element.offsetHeight}px`),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const back = () => {
    focusImageNext(imageId);
    // Back where it was opened (the gallery as it was, a fixed version's list); else the gallery.
    closeLoupe(datasetId, () => go({ screen: "gallery", datasetId, stage, recordId, plan }));
  };
  // One chosen object for the image, the list and the check's lines (the route's obj): a move
  // inside the loupe, not another place in the history.
  const choose = (id: string | null) =>
    goReplacing({ screen: "loupe", datasetId, imageId, stage, recordId, objectId: id, plan });
  const step = (by: number) => {
    const next = items[index + by];
    if (next)
      goReplacing({ screen: "loupe", datasetId, imageId: next.image.id, stage, recordId, plan });
  };
  // ← → step through the images, as the buttons do (Sol 2026-10-12, 10-13; FiftyOne and VIA do
  // the same), not while writing; a fix is recorded on stepping, as by the buttons.
  const stepRef = useRef(step);
  stepRef.current = step;
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable=true]")) return;
      if (event.key === "ArrowRight") stepRef.current(1);
      if (event.key === "ArrowLeft") stepRef.current(-1);
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);

  // The boxes about this image, in the same band as the gallery's (design 4.3). A box shown
  // from the talk: here when it is about this image, else in its stage's gallery.
  const proposals = useApi<{ proposals: Proposal[] }>(`${base}/proposals`);
  const place = `image:${imageId}`;
  const [shownRight] = useShownOnRight(datasetId);
  const band = useBand(
    datasetId,
    place,
    // A run of Apply is the ring's (definition 40.2), not a band's.
    boxesAbout(proposals.data?.proposals ?? [], imageId).filter(
      (p) => !isApplyRun(p) && shownRight.includes(p.id),
    ),
  );
  const [viewed] = useViewedBox(datasetId);
  const viewedBox = useApi<Proposal>(viewed ? `/v1/proposals/${viewed}` : null);
  const talking = workerAt("dataset");
  const talkTo = useTalkTo(datasetId);

  // Used for training: green; not: an empty ring, pressed to use this record's result (and
  // pressed again, as on the cards, the image is left out); taken back from the notice.
  const recordMark =
    shownRecord && !shownRecord.cannot && !annotating
      ? {
          mark: (shownRecord.used ? "adopted" : "ran") as UseMarkKind,
          onToggle: (adopt: boolean) => {
            const before = records.data?.results.find((r) => r.used)?.result_id ?? null;
            const path = `/v1/datasets/${datasetId}/images/${imageId}/adoption`;
            const put = (id: string | null) =>
              id
                ? api(path, { method: "PUT", body: { result_id: id } })
                : api(path, { method: "DELETE" });
            void (adopt ? put(shownRecord.result_id) : markUsed(imageId, false))
              .then(() => {
                invalidate(datasetId);
                toast.success(t(adopt ? "select.use.done" : "select.unuse.done", { count: 1 }), {
                  action: {
                    label: t("select.undo"),
                    onClick: () =>
                      void (adopt ? put(before) : markUsed(imageId, true))
                        .then(() => invalidate(datasetId))
                        .catch((reason) => toast.error(errorText(reason))),
                  },
                });
              })
              .catch((reason) => toast.error(errorText(reason)));
          },
        }
      : null;

  // ②'s mark over the image, as on its card: a record looked at while using for training; else
  // used for training or left out, and while annotating with AI the cards' choosing ring.
  const mark: LoupeMark = item
    ? (recordMark ??
      (stage === "production" && (!recordId || annotating)
        ? {
            // ②: the same mark as on the card, used for training or left out; while
            // annotating with AI, annotated or not (user 2026-10-14).
            mark: markOf(item),
            // While annotating with AI, the same choosing ring as the cards'.
            ...(purpose === "annotate"
              ? {
                  choose: {
                    chosen: picks.includes(item.image.id),
                    done: annotated(item),
                    label: ringLabel(item),
                    onChoose: (on: boolean) =>
                      decision.setImages(toggled(picks, item.image.id, on)),
                  },
                }
              : {}),
            onToggle: (adopt: boolean) =>
              void markUsed(item.image.id, adopt)
                .then(() => {
                  reload();
                  // As on the cards: taken back from the notice.
                  toast.success(t(adopt ? "select.use.done" : "select.unuse.done", { count: 1 }), {
                    action: {
                      label: t("select.undo"),
                      onClick: () =>
                        void markUsed(item.image.id, !adopt)
                          .then(reload)
                          .catch((reason) => toast.error(errorText(reason))),
                    },
                  });
                })
                .catch((reason) => toast.error(errorText(reason))),
          }
        : null))
    : null;
  // As in the gallery: the label colours (with this image's counts) and the display, behind the
  // eye (user 2026-10-13), right over the image as every list's (user 2026-10-28). A record's
  // results: its version's labels; else the plan seen (37.3).
  const eye = (shown: GalleryItem) => (
    <SetEye
      datasetId={datasetId}
      plan={
        recordId && shown.badge.record_revision ? { revision: shown.badge.record_revision } : plan
      }
      counts={labelCountsOf(shown)}
    />
  );
  // The side, the same whether the result is fixed here or only looked at: the editor gives its
  // objects and what finishing does.
  const side = (shown: GalleryItem, objects: ReactNode, note: ReactNode) => (
    <LoupeSide
      datasetId={datasetId}
      item={shown}
      view={annotating ? "run" : sideView(stage, recordId)}
      recordId={recordId ?? (annotating ? (shown.badge.record_id ?? null) : null)}
      training={!annotating}
      selected={objectId}
      onSelect={choose}
      colors={page.data?.label_colors ?? {}}
      objects={objects}
      actions={
        <LoupeActions reference={answer ? { datasetId, imageId, resultId: answer } : undefined}>
          {note}
        </LoupeActions>
      }
    />
  );

  return (
    <AgentShell
      datasetId={datasetId}
      looking={{
        stage,
        ...(item ? { image_id: item.image.id, image_name: item.image.name } : {}),
        // Where ← → go, so "next" asked of the steward is this next (definition 59.3).
        ...(item && items[index - 1] ? { previous_image: items[index - 1].image.name } : {}),
        ...(item && items[index + 1] ? { next_image: items[index + 1].image.name } : {}),
        ...(recordId ? { record_id: recordId, record_number: item?.badge.record_number } : {}),
        ...seen,
      }}
    >
      <div className="flex min-h-screen flex-col">
        {/* Stays at the top on a tall image (Astra 2026-10-05: close and next went out of view),
          with the "seeing" row: both are measured, so the right panel ends at the window's
          foot (Astra 2026-10-06: a save button began below it). */}
        <div ref={head} className="top-0 z-20 min-[1000px]:sticky">
          <header className="flex flex-wrap items-center gap-x-3.5 gap-y-2 border-b border-line bg-sheet px-5 py-2.5">
            {/* One image of the gallery, looked at large: no path down a level (user
                2026-10-14); closing is right above the image. */}
            <h1 className="m-0 text-title">{item?.image.name ?? "…"}</h1>
            <span className="text-muted-foreground">{dataset.data?.name ?? "…"}</span>
            <span className="text-muted-foreground">
              {index >= 0 && t("loupe.position", { at: index + 1, total: items.length })}
            </span>
            <span className="flex-1" />
            <JobsButton datasetId={datasetId} />
            <SettingsButton />
            <ThemeToggle />
          </header>
          <div
            className={`flex flex-wrap items-center gap-x-3.5 gap-y-1.5 border-b-2 px-5 py-2 ${
              stage === "production" ? "border-annotated bg-surface" : "border-action bg-surface"
            }`}
          >
            {/* Moving through the images and closing, right above the image (user 2026-10-13:
                far at the top right with the jobs, "close" was not found). */}
            {/* Close first and apart, the pair of steps after it (user 2026-10-16: often a look
                and close; the steps are one pair). Purple: something to press, found at once on
                a busy screen. */}
            <span className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
              <Button size="small" variant="primary" onClick={back}>
                {t("common.close")}
              </Button>
              <span className="flex items-center gap-1.5">
                <Button size="small" disabled={index <= 0} onClick={() => step(-1)}>
                  {t("loupe.previous")}
                </Button>
                <Button
                  size="small"
                  disabled={index < 0 || index >= items.length - 1}
                  onClick={() => step(1)}
                >
                  {t("loupe.next")}
                </Button>
              </span>
            </span>
            {changed && <b className="text-heading">{t("fix.editing")}</b>}
            <span className="text-muted-foreground">
              {changed
                ? t("fix.base")
                : item?.badge.kind === "result"
                  ? t(
                      // Whose it is and why it is used (types design 7.2): a person's fix, a
                      // person's choice, or the rule's newest.
                      item.badge.by === "human"
                        ? "loupe.adopted.human"
                        : item.badge.by === "import"
                          ? "loupe.adopted.imported"
                          : item.badge.picked
                            ? "loupe.adopted.picked"
                            : "loupe.adopted.from",
                      {
                        time: when(item.badge.record_at),
                        model: modelLabel(item.badge.model, item.badge.record_kind, modelName),
                      },
                    )
                  : seenRecord
                    ? // The record looked at, as the gallery says it (Astra 2026-10-06: it was
                      // gone).
                      t("loupe.seeing.run", {
                        time: when(seenRecord.record_at),
                        model: modelLabel(seenRecord.model, seenRecord.record_kind, modelName),
                        version: seenRecord.trial
                          ? t("run.trial.version", {
                              version: versionOf(seenRecord.record_revision ?? 0),
                            })
                          : versionOf(seenRecord.record_revision ?? 0),
                      })
                    : // A result of a run is the AI's annotation (Astra 2026-10-17: a trial's
                      // result was called "the AI's guess").
                      t(stage === "instruction" ? "loupe.readonly.result" : "loupe.readonly")}
            </span>
          </div>
        </div>
        {viewedBox.data && viewed === viewedBox.data.id && (
          <DecidedBand
            datasetId={datasetId}
            proposal={viewedBox.data}
            talking={talking}
            onTalk={talkTo}
            className="mx-5 mt-3"
          />
        )}
        <DecisionBand
          datasetId={datasetId}
          band={band}
          talking={talking}
          onTalk={talkTo}
          nameOf={(id) => all.find((i) => i.image.id === id)?.image.name}
          className="mx-5 mt-3"
          sticky=""
        />
        {item && fixable && answer ? (
          <ResultEditor
            // A new result shown (a run done meanwhile) starts again from it.
            key={`${item.image.id}:${answer}`}
            datasetId={datasetId}
            imageId={item.image.id}
            width={item.image.width}
            height={item.image.height}
            resultId={answer}
            annotations={item.annotations}
            definitions={instruction.data?.label_definitions ?? []}
            colors={page.data?.label_colors ?? {}}
            chosen={objectId}
            // Used for training: not left out and with a result the rule takes (the loupe's view
            // names it "result" or by its status).
            used={!item.image.excluded && hasAnswer(item.badge)}
            overlay={
              mark && <UseMark mark={mark.mark} onToggle={mark.onToggle} choose={mark.choose} />
            }
            onChanged={setChanged}
            side={({ objects, note }) => side(item, objects, note)}
            eye={eye(item)}
          />
        ) : item ? (
          <div className="flex flex-1 flex-wrap">
            <main className="flex min-w-0 flex-[999_1_420px] flex-col">
              {/* How it looks, right over the image as in the tools' row (user 2026-10-28). */}
              <div className="flex justify-end px-5 pt-2">{eye(item)}</div>
              <LoupeView
                item={item}
                colors={page.data?.label_colors ?? {}}
                selected={objectId}
                onSelect={choose}
                mark={mark}
              />
            </main>
            {side(
              item,
              null,
              answer ? (
                <p className="m-0 text-body text-muted-foreground">{t("fix.mask.readonly")}</p>
              ) : null,
            )}
          </div>
        ) : (
          <p className="px-5 text-muted-foreground">{page.error ? errorText(page.error) : "…"}</p>
        )}
      </div>
    </AgentShell>
  );
}

/** What the side panel tells of the image: ① the image, ② what training gets, or a run's
 * result. */
function sideView(stage: StageName, recordId: string | null): View {
  if (stage === "instruction") return "images";
  return recordId ? "run" : "adoption";
}

/** How many objects of each label the image has (the label colours' counts). */
function labelCountsOf(item: GalleryItem): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const a of item.annotations) counts[a.label] = (counts[a.label] ?? 0) + 1;
  return counts;
}
