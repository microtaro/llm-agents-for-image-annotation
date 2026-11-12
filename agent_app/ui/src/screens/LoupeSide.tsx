// The loupe's side: where what is shown came from (result, why adopted), the annotations one by
// one, and the run results of the image.
import { type ReactNode, useEffect, useRef } from "react";
import type { GalleryItem, RecordKind, ResultBy, View } from "@/api/types";
import { LabelDot } from "@/components/LabelColors";
import { t, when } from "@/i18n";
import { showInSide } from "@/lib/panelScroll";
import { formatRoute, goReplacing, type Route } from "@/lib/route";
import { modelLabel, spentText, versionOf, useModelName } from "@/lib/runChoice";
import { buildRows, noAnswer } from "@/lib/table";
import { invalidate, useApi } from "@/lib/useApi";
import { api } from "@/api/client";
import { errorText } from "@/lib/errorText";
import { toast } from "sonner";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { shownPills } from "./GalleryCard";

export function LoupeSide({
  datasetId,
  item,
  view,
  selected = null,
  onSelect = () => {},
  actions,
  colors = {},
  recordId = null,
  training = true,
  objects = null,
}: {
  datasetId: string;
  /** Label -> color, for the mark beside each object in the list. */
  colors?: Record<string, string>;
  item: GalleryItem;
  view: View;
  /** The chosen object, shared with the image. */
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  /** What can be done with the image, shown first (LoupeActions). */
  actions?: ReactNode;
  /** The annotation record shown on the image (none: the one training uses). */
  recordId?: string | null;
  /** What training uses can be chosen here (not while annotating with AI, user 2026-10-14). */
  training?: boolean;
  /** The objects as the result's fix has them, in place of the list of the result's (the loupe
   * looks and fixes on one image, user 2026-10-27). */
  objects?: ReactNode;
}) {
  const modelName = useModelName();
  // The object chosen on the image brought into view in this list (Astra 2026-10-06: it was
  // marked, but below the panel's scroll).
  const side = useRef<HTMLElement>(null);
  // Again as the panel's other parts arrive and push the list down (Astra 2026-10-06: opened
  // from the table, the chosen line sat below the window).
  useEffect(() => {
    if (!selected) return;
    const show = () => {
      showInSide(side.current?.querySelector(`[data-object="${CSS.escape(selected)}"]`));
    };
    show();
    const timers = [300, 1000].map((ms) => window.setTimeout(show, ms));
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [selected]);
  return (
    <aside
      ref={side}
      className="flex max-w-[360px] flex-[1_1_320px] flex-col border-l border-line bg-sheet sticky top-(--loupe-head) max-h-[calc(100vh-var(--loupe-head))] self-start overflow-auto"
    >
      {actions}
      <section className="flex flex-col gap-2 border-b border-line px-4.5 py-3">
        <h2 className="m-0 text-heading">
          {/* Said as it is: nothing adopted is not "why this is adopted" (Astra 2026-10-06). */}
          {view === "adoption" && item.badge.kind !== "result"
            ? t("loupe.side.adoption.none")
            : t(`loupe.side.${view}`)}
        </h2>
        <dl className="m-0 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-body">
          {/* The same pill as on the card (Astra 2026-10-06: plain text here, a green pill
              there). In ① the image as imported: adoption is shown in ②. */}
          <dt className="text-muted-foreground">{t("loupe.state")}</dt>
          <dd className="m-0">
            {view === "images" ? (
              t("loupe.state.images")
            ) : (
              <>
                {/* The card's pills where it has them (user 2026-10-14: a green "annotated"
                    here read as the green of "used for training"). */}
                {shownPills(item, view).length ? (
                  <span className="inline-flex flex-wrap gap-1">
                    {shownPills(item, view).map((pill) => (
                      <span key={pill.text} className={pill.look}>
                        {pill.text}
                      </span>
                    ))}
                  </span>
                ) : (
                  "—"
                )}
              </>
            )}
          </dd>
          {item.badge.elapsed_ms != null && (
            // The time and cost the card shows in a run, kept here in every stage.
            <FactRow
              name={t("loupe.spent")}
              value={spentText(item.badge.elapsed_ms, item.badge.cost_usd)}
            />
          )}
          {item.badge.kind === "result" && (
            <FactRow
              name={t("loupe.adopted.run")}
              value={`${when(item.badge.record_at)} · ${modelLabel(item.badge.model, item.badge.record_kind, modelName)}`}
            />
          )}
          {(item.badge.checked || item.badge.other) && (
            // By the criteria the image is judged by (definition 85.6): said only when they
            // are another plan's, or a person checked it.
            <FactRow
              name={t("loupe.criteria")}
              value={
                item.badge.checked
                  ? t("loupe.criteria.checked")
                  : t("loupe.criteria.other", { revision: item.badge.record_revision ?? "" })
              }
            />
          )}
          <FactRow
            name={t("loupe.source")}
            value={item.image.source_path ?? t("dataset.source.unknown")}
          />
          <FactRow name={t("loupe.origin")} value={t(`image.origin.${item.image.origin}`)} />
          <FactRow
            name={t("loupe.size")}
            value={t("loupe.size.value", { width: item.image.width, height: item.image.height })}
          />
        </dl>
        <WorkerNote datasetId={datasetId} imageId={item.image.id} resultId={item.badge.result_id} />
      </section>
      {objects ?? (
        <>
          {/* The objects shown on the image, above the records (user 2026-10-27: they were under
          the records' history, off the screen). */}
          <section className="flex flex-col gap-1.5 border-b border-line px-4.5 py-3">
            <details open>
              <summary className="cursor-pointer font-semibold">
                {noAnswer(item, view)
                  ? t("loupe.objects.noResult")
                  : t("loupe.objects", { count: item.annotations.length })}
              </summary>
              <ol className="m-0 mt-1.5 flex flex-col gap-0.5 pl-5 text-body">
                {/* Children under their parent, as in the table (step 13 design 2). */}
                {buildRows([item]).map((row) =>
                  row.annotationId ? (
                    <li key={row.key} style={{ marginLeft: `${row.depth * 1.25}rem` }}>
                      {/* Chooses the object on the image too (Astra 2026-10-06: it did not). */}
                      <button
                        type="button"
                        data-object={row.annotationId}
                        onClick={() =>
                          onSelect(row.annotationId === selected ? null : row.annotationId)
                        }
                        // Chosen: a light ground and bold.
                        className={`cursor-pointer rounded-sm px-0.5 text-left ${row.annotationId === selected ? "bg-selected font-semibold text-selected-ink" : ""}`}
                      >
                        <LabelDot color={colors[row.label]} />
                        {row.number ? `${row.label} ${row.number}` : row.label}
                        {Object.entries(row.values).map(([name, value]) => ` · ${name} ${value}`)}
                      </button>
                    </li>
                  ) : null,
                )}
              </ol>
            </details>
          </section>
        </>
      )}
      <ResultList
        datasetId={datasetId}
        imageId={item.image.id}
        // In ② each record is looked at on the image, then chosen for training (7.2).
        recordId={recordId}
        choosing={training && view !== "images"}
        // Annotating with AI: choosing a record makes it the annotation (user 2026-10-16).
        switching={!training}
        used={!item.image.excluded}
        picked={Boolean(item.badge.picked)}
      />
    </aside>
  );
}

function FactRow({ name, value }: { name: string; value: string }) {
  return (
    <>
      <dt className="text-muted-foreground">{name}</dt>
      <dd className="m-0 break-all">{value}</dd>
    </>
  );
}

/** What the AI wrote when it ended (user 2026-10-16: it was kept but shown nowhere, and an AI
 * that did not annotate said so only there). A failure's reason open; otherwise folded, read
 * when wanted (its words differ from image to image). */
function WorkerNote({
  datasetId,
  imageId,
  resultId,
}: {
  datasetId: string;
  imageId: string;
  resultId?: string;
}) {
  // The same list as the records below, so no other request.
  const list = useApi<{ results: ResultRef[] }>(
    resultId ? `/v1/datasets/${datasetId}/images/${imageId}/results` : null,
  );
  const record = list.data?.results.find((r) => r.result_id === resultId);
  if (!record?.message || record.by === "human") return null;
  const failed = record.status === "failed";
  return (
    <details open={failed} className="text-body">
      <summary className="cursor-pointer text-muted-foreground">
        {t(failed ? "loupe.note.failed" : "loupe.note")}
      </summary>
      <p className="m-0 mt-1 whitespace-pre-wrap">{record.message}</p>
    </details>
  );
}

export interface ResultRef {
  result_id: string;
  /** Its record: a run, or a person's fix (definition 21.4); run_id only for a run's. */
  record_id: string;
  record_number?: number;
  run_id: string | null;
  by: ResultBy;
  record_kind: RecordKind;
  trial?: boolean;
  record_at: string;
  model: string | null;
  instruction_revision: number;
  status: string;
  /** What the AI wrote when it ended (a failure's reason). */
  message?: string | null;
  annotation_count: number;
  elapsed_ms: number | null;
  cost_usd: string | null;
  /** The image's annotation now (whether training uses it or not). */
  now?: boolean;
  /** The one training uses now. */
  used?: boolean;
  /** Why training cannot use it (none: it can). */
  cannot?: "failed" | "draft" | "requirement" | null;
}

/** Every annotation record of this image, newest first, not folded (user 2026-10-13: look on
 * the image first, then choose). Pressing one only shows its result on the image (the loupe on
 * that record; user 2026-10-19: one pressed to look at was chosen); beside the one shown,
 * "Use this record" chooses it (a person's own decision, done at once). */
function ResultList({
  datasetId,
  imageId,
  recordId,
  choosing,
  switching = false,
  used = true,
  picked,
}: {
  datasetId: string;
  imageId: string;
  /** From annotating with AI: the chosen record becomes the image's annotation (and training
   * uses it if the image is used; user 2026-10-16). */
  switching?: boolean;
  /** The image is used for training (said before switching). */
  used?: boolean;
  /** The record shown on the image (none: the one training uses). */
  recordId: string | null;
  /** In ② a record can be chosen for training. */
  choosing: boolean;
  /** A person chose it (else the rule's newest). */
  picked: boolean;
}) {
  const modelName = useModelName();
  const list = useApi<{ results: ResultRef[] }>(
    `/v1/datasets/${datasetId}/images/${imageId}/results`,
  );
  const results = list.data?.results ?? [];
  const path = `/v1/datasets/${datasetId}/images/${imageId}/adoption`;
  const shown = recordId ?? results.find((r) => r.used)?.record_id ?? null;
  async function switchTo(r: ResultRef) {
    // Chosen, not copied: going back and forth adds no record (user 2026-10-16).
    const made = await pickOnly(r.result_id);
    if (!made) return;
    toast.success(t(used ? "loupe.switch.done.used" : "loupe.switch.done"), {
      // One notice, of the record chosen last: switching again replaces it rather than
      // stacking one per press (user 2026-10-16).
      id: `switch-${imageId}`,
      duration: 10000,
      action: {
        label: t("select.undo"),
        // The one a person chose before, or the rule's.
        onClick: () => void (made.before ? pickOnly(made.before) : change(null)),
      },
    });
  }
  async function use(r: ResultRef) {
    // Back to what was used before: a person's choice, or the rule's newest.
    const before = picked ? (results.find((x) => x.used)?.result_id ?? null) : null;
    if (!(await change({ result_id: r.result_id }))) return;
    toast.success(t("loupe.use.done"), {
      // One notice, of the record pressed last (as annotating's).
      id: `use-${imageId}`,
      duration: 10000,
      action: {
        label: t("select.undo"),
        onClick: () => void change(before ? { result_id: before } : null),
      },
    });
  }
  // Annotating: chosen, the image used or not as it was (definition 19.4).
  async function pickOnly(resultId: string) {
    try {
      const made = await api<{ before: string | null }>(
        `/v1/datasets/${datasetId}/images/${imageId}/switch`,
        { body: { result_id: resultId } },
      );
      invalidate(datasetId);
      return made;
    } catch (reason) {
      toast.error(errorText(reason));
      return null;
    }
  }
  async function change(body: { result_id: string } | null) {
    try {
      await api(path, body ? { method: "PUT", body } : { method: "DELETE" });
      invalidate(datasetId);
      return true;
    } catch (reason) {
      toast.error(errorText(reason));
      return false;
    }
  }
  return (
    <section
      aria-label={t("loupe.results", { count: results.length })}
      className="flex flex-col gap-1.5 border-b border-line px-4.5 py-3"
    >
      <b>{t("loupe.results", { count: results.length })}</b>
      {choosing && picked && (
        <div className="flex flex-wrap items-center gap-2 text-body">
          {t("loupe.results.picked")}
          <Button size="small" onClick={() => void change(null)}>
            {t("loupe.results.rule")}
          </Button>
        </div>
      )}
      {results.length === 0 && (
        <p className="m-0 text-body text-muted-foreground">{t("loupe.results.none")}</p>
      )}
      {choosing && results.length > 1 && (
        <p className="m-0 text-small text-muted-foreground">{t("loupe.use.how")}</p>
      )}
      {switching && results.length > 1 && (
        <p className="m-0 text-small text-muted-foreground">
          {t(used ? "loupe.switch.how.used" : "loupe.switch.how")}
        </p>
      )}
      <ul className="m-0 flex flex-col gap-1 pl-0 text-body">
        {results.map((r) => {
          const recordRoute = (recordId: string): Route => ({
            screen: "loupe",
            datasetId,
            imageId,
            stage: "production",
            recordId,
          });
          const on = r.record_id === shown;
          const usable = !r.cannot;
          // What choosing changes: the image's annotation while annotating, else what
          // training uses.
          const current = switching ? r.now : r.used;
          return (
            <li
              key={r.result_id}
              // A box to press, as the cards are (user 2026-10-13: with no frame, it was not
              // clear the records could be pressed); the shown one framed in the action colour.
              className={`relative flex list-none flex-col gap-0.5 rounded-md py-1 pr-2 pl-2 ${on ? "border-2 border-action bg-surface" : "border border-line bg-surface hover:bg-hover"}`}
            >
              <a
                aria-current={on ? "true" : undefined}
                href={formatRoute(recordRoute(r.record_id))}
                // Another record of the same image is a move inside the loupe.
                onClick={(event) => {
                  event.preventDefault();
                  goReplacing(recordRoute(r.record_id));
                }}
                // The whole box shows it; its button stays above.
                className={`no-underline after:absolute after:inset-0 ${on ? "font-semibold" : ""}`}
              >
                {t("run.number", { number: r.record_number ?? "" })}
                {r.trial ? t("run.trial.paren") : ""} · {when(r.record_at)} ·{" "}
                {modelLabel(r.model, r.record_kind, modelName)} ·{" "}
                {versionOf(r.instruction_revision)}
              </a>
              <span className="text-muted-foreground">
                {[
                  t(`badge.${r.status}`),
                  t("common.objects", { count: r.annotation_count }),
                  spentText(r.elapsed_ms, r.cost_usd),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
              {switching && r.now && (
                <span className="flex items-center gap-1 font-semibold">
                  <Check className="size-4" aria-hidden />
                  {t("loupe.switch.current")}
                </span>
              )}
              {choosing && r.used && (
                <span className="font-semibold text-annotated-ink">{t("loupe.results.used")}</span>
              )}
              {(choosing || switching) && on && !current && usable && (
                // Above the box's link, so pressing it chooses and pressing the rest only looks.
                <Button
                  size="small"
                  variant={choosing ? "use" : undefined}
                  className="relative z-10 self-start"
                  onClick={() => void (switching ? switchTo(r) : use(r))}
                >
                  {t("loupe.record.choose")}
                </Button>
              )}
              {on && !usable && (
                // A record that cannot be chosen is only looked at, and says why.
                <span className="text-muted-foreground">
                  {t(`loupe.results.cannot.${r.cannot}`)}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
