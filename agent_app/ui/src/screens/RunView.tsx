// A run on the right (agent app 4.3, prototype 2's form): on the step where the AI works, the
// run of that stage instead of the cards of the stage. How far it is (succeeded, failed,
// working, waiting), what it costs against its limit, its images as every list of images is
// (ImageSet), a failed image's "Again" (a person's own decision, the same settings), and the run
// before it in one line.
import { toast } from "sonner";
import { api } from "@/api/client";
import type { GalleryPage, Run } from "@/api/types";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { againBody } from "@/lib/actions";
import { errorText } from "@/lib/errorText";
import { planOf } from "@/lib/route";
import { actorName } from "@/lib/actors";
import { useModelName, versionOf } from "@/lib/runChoice";
import { runParts } from "@/lib/talk";
import { invalidate, useApi } from "@/lib/useApi";
import { runState } from "@/lib/work";
import { budgetWords } from "@/lib/selection";
import { ImageSet } from "./ImageSet";

const SEGMENT = {
  succeeded: "bg-annotated",
  working: "bg-processing",
  failed: "bg-failed",
  waiting: "bg-selected",
} as const;

/** A cost as dollars to three places (the server keeps more). */
function dollars(usd: string | null | undefined): string {
  const value = Number(usd ?? 0);
  return Number.isFinite(value) ? value.toFixed(3) : "0.000";
}

export function RunView({
  datasetId,
  run,
  previous,
  colors,
}: {
  datasetId: string;
  run: Run;
  previous: Run | null;
  colors: Record<string, string>;
}) {
  const page = useApi<GalleryPage>(
    `/v1/datasets/${datasetId}/gallery?view=run&record_id=${run.id}`,
  );
  const name = useModelName();
  // The run's own images (the run view lists the others too, as "not in this run").
  const items = (page.data?.items ?? []).filter((i) => i.badge.kind !== "not_in_run");
  const parts = runParts(
    items.map((i) => i.badge),
    run.total,
  );
  const going = run.going;
  const left = run.total - run.processed;

  async function stop() {
    try {
      await api(`/v1/runs/${run.id}/stop`, { body: {} });
    } catch (reason) {
      toast.error(errorText(reason));
    } finally {
      invalidate(datasetId);
    }
  }
  async function again(body: Record<string, unknown>) {
    try {
      await api(`/v1/datasets/${datasetId}/runs/${crypto.randomUUID()}`, {
        method: "PUT",
        body,
      });
      toast.success(t("run.view.againDone"));
    } catch (reason) {
      toast.error(errorText(reason));
    } finally {
      invalidate(datasetId);
    }
  }

  return (
    <section aria-label={t("run.view.label")} className="flex flex-col gap-2.5 px-5 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <b className="text-heading">
          {t("run.view.title", {
            total: run.total,
            state: t(going ? "run.view.going" : "run.view.done"),
            done: run.processed,
          })}
          {parts.failed > 0 && ` ${t("run.view.failedCount", { count: parts.failed })}`}
        </b>
        <span className="text-body text-muted-foreground">
          {[name(run.settings.model), run.settings.effort, versionOf(run.instruction_revision)]
            .filter(Boolean)
            .join(" · ")}
        </span>
        {run.decision && (
          // Who decided it, and the worker whose box it was (definition 21.3).
          <span className="text-body text-muted-foreground">
            {run.decision.requested_by === run.decision.decided_by
              ? t("run.view.decided", { who: actorName(run.decision.decided_by) })
              : t("run.view.decidedAsked", {
                  who: actorName(run.decision.decided_by),
                  asked: actorName(run.decision.requested_by),
                })}
          </span>
        )}
        <span className="flex-1" />
        <UseRunButton datasetId={datasetId} run={run} />
        {going && (
          <>
            <span className="text-xs text-muted-foreground">{t("run.view.stopHint")}</span>
            <Button size="small" className="text-failed" onClick={() => void stop()}>
              {t("work.job.stop")}
            </Button>
          </>
        )}
      </div>
      <div
        role="img"
        aria-label={t("run.view.bar", parts)}
        className="flex h-2.5 overflow-hidden rounded-full bg-selected"
      >
        {(["succeeded", "working", "failed"] as const).map((key) => (
          <span
            key={key}
            className={SEGMENT[key]}
            style={{ width: `${run.total ? (parts[key] / run.total) * 100 : 0}%` }}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-body">
        {(Object.keys(SEGMENT) as (keyof typeof SEGMENT)[]).map((key) => (
          <span key={key} className="inline-flex items-center gap-1.5">
            <span className={`inline-block size-2.5 rounded-sm ${SEGMENT[key]}`} />
            {t(`run.view.part.${key}`)} {parts[key]}
          </span>
        ))}
        <span className="text-muted-foreground">
          {t("run.view.left", { count: left })} ·{" "}
          {run.budget_per_image_usd
            ? t("run.view.cost", {
                cost: dollars(run.cost?.usd),
                ...budgetWords(run.budget_per_image_usd, run.total),
              })
            : t("run.view.costNoLimit", { cost: dollars(run.cost?.usd) })}
        </span>
      </div>
      {previous && (
        <div className="text-body text-muted-foreground">
          {t("run.view.previous", {
            run: previous.number ?? "?",
            total: previous.total,
            model: name(previous.settings.model),
            ok: previous.succeeded,
            failed: previous.processed - previous.succeeded,
            state: t(`run.status.${runState(previous.status, previous.error_code)}`),
          })}
        </div>
      )}
      <ImageSet
        datasetId={datasetId}
        items={items}
        view="run"
        colors={colors}
        plan={planOf({ revision: run.instruction_revision })}
        title={t("gallery.list", { count: items.length })}
        recordId={run.id}
        cardAction={(item) => {
          const body = againBody(run, item.image.id);
          return (
            body &&
            !going &&
            !item.badge.succeeded &&
            !item.badge.waiting && (
              <Button size="small" className="mt-1" onClick={() => void again(body)}>
                {t("run.view.again")}
              </Button>
            )
          );
        }}
      />
    </section>
  );
}

/** "Use this record's n for training" (types design 17.2): only the record's images, with its
 * results; the others stay as they are. None for a trial or while it goes on. */
function UseRunButton({ datasetId, run }: { datasetId: string; run: Run }) {
  // The plan's requirement now: a record of an earlier one cannot be used (Sol 2026-10-13: the
  // loupe said "cannot be used" while this button offered it).
  if (run.earlier && !run.going && run.succeeded)
    return <span className="text-body text-muted-foreground">{t("run.use.earlier")}</span>;
  if (!run.usable) return null;
  async function use() {
    try {
      const done = await api<{ images: number }>(`/v1/runs/${run.id}/use`, { body: {} });
      toast.success(t("run.use.done", { count: done.images, run: run.number ?? "?" }));
      invalidate(datasetId);
    } catch (reason) {
      toast.error(errorText(reason));
    }
  }
  return (
    // Green: it changes what training uses at once (DESIGN.md 6).
    <Button size="small" variant="use" onClick={() => void use()}>
      {t("run.use", { count: run.succeeded, run: run.number ?? "?" })}
    </Button>
  );
}
