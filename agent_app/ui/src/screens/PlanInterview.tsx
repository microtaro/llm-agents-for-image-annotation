// The plan's screen (definition 26.7): the plan worker interviews on the left, and the right shows
// what the talk shows (PlanFocus: the past requirements, whether a label is the same, the samples,
// a record's results; at the entry, the facts and the existing plans, 34.2) above the plan as the
// answers made it (folded to one line meanwhile). With nothing above, the plan opened. The entry starts by
// itself when the plan has no version yet.
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type {
  AgentEvent,
  Dataset,
  GalleryPage,
  Instruction,
  PlanItemName,
  PlanState,
  Proposal,
  Run,
} from "@/api/types";
import type { FigureImage } from "@/components/PlanFigure";
import { Dialog } from "@/components/ui/dialog";
import { t } from "@/i18n";
import type { PlanTarget } from "@/lib/decisions";
import { workerAt } from "@/lib/home";
import { newestTrial } from "@/lib/planParts";
import { go, type PlanRef, planOf, planQuery } from "@/lib/route";
import { invalidate, useApi } from "@/lib/useApi";
import { useRunWatch } from "@/lib/useRunWatch";
import { type About, planAbout } from "@/lib/talk";
import { useChatOf } from "@/lib/viewState";
import { AgentShell } from "./AgentShell";
import { GalleryHeader } from "./GalleryHeader";
import { PlanBasis } from "./PlanBasis";
import { PlanBook } from "./PlanBook";
import { planFocus } from "./PlanFocus";
import { PlanImages } from "./PlanImages";
import { PlanScreen } from "./PlanScreen";
import { RunBar } from "./RunBar";
import { TrialView } from "./TrialView";

export function PlanInterview({
  datasetId,
  plan,
  about,
  recordId,
}: {
  datasetId: string;
  /** The plan the talk is about (definition 36.1): said at the top, kept on switching. */
  plan: PlanRef | null;
  /** What the right was sent to show above the plan (definition 37.4); none: the newest line. */
  about: About | null;
  /** A record of samples shown above the plan it ran, an earlier plan's too (user 2026-10-27:
   * an old trial's samples could not be seen together). */
  recordId: string | null;
}) {
  const base = `/v1/datasets/${datasetId}`;
  const dataset = useApi<Dataset>(base);
  const state = useApi<PlanState>(`${base}/plan/state`);
  const page = useApi<GalleryPage>(`${base}/gallery?view=images`);
  const runs = useApi<{ runs: Run[] }>(`${base}/runs`);
  const proposals = useApi<{ proposals: Proposal[] }>(`${base}/proposals`);
  const [chatOf] = useChatOf(datasetId);
  // The dataset's worker's talk (by its place, 48.11).
  const worker = workerAt("dataset");
  const chosen = chatOf[worker];
  const events = useApi<{ events: AgentEvent[] }>(
    `${base}/agents/${worker}/events${chosen ? `?chat=${chosen}` : ""}`,
  );
  const draft = Boolean(state.data?.write_id);
  const latest = useApi<Instruction>(draft ? `${base}/instructions/latest` : null);
  const [planShown, setPlanShown] = useState<PlanTarget | null>(null);
  const reloadAll = () => invalidate(datasetId);
  const { active } = useRunWatch(runs.data?.runs ?? [], reloadAll);

  // The plan's entry starts by itself in an empty chat of a plan with no version, a new chat too
  // (definition 34.2; the server does nothing otherwise).
  useEffect(() => {
    void api(`${base}/plan/interview`, { method: "POST" })
      .then(() => invalidate(datasetId))
      .catch(() => undefined);
  }, [base, datasetId, chosen]);

  const images = new Map<string, FigureImage>(
    (page.data?.items ?? []).map((i) => [i.image.id, i.image]),
  );
  const colors = page.data?.label_colors ?? {};
  // The images as a plan's screen draws its references.
  const planImages = new Map((page.data?.items ?? []).map((i) => [i.image.id, i.image]));
  const lines = events.data?.events ?? [];
  const question = lines.filter((e) => e.kind === "question" && !e.closed_at).at(-1);
  const asking = (question?.data?.item ?? null) as PlanItemName | null;
  const trialBox = (proposals.data?.proposals ?? []).find(
    (p) => p.waiting && p.tool === "run_start" && p.args.trial === true,
  );
  const trialRun = newestTrial(runs.data?.runs ?? [], active?.id);
  const boxOf = (id: string) => (proposals.data?.proposals ?? []).find((p) => p.id === id);
  const runOf = (runId: string) => {
    const run = (runs.data?.runs ?? []).find((r) => r.id === runId);
    return run ? { trial: Boolean(run.trial), revision: run.instruction_revision } : undefined;
  };
  // A plan chosen at the top other than the plan now (definition 56); a blank plan is no plan.
  const now = state.data ? planOf(state.data) : null;
  const earlier =
    plan && !("blank" in plan) && (!now || planQuery(plan) !== planQuery(now)) ? plan : null;
  const focus = planFocus({
    datasetId,
    lines,
    about: planAbout(lines, about, boxOf, runOf),
    images,
    trialBox,
    trialRun,
  });

  return (
    <AgentShell
      datasetId={datasetId}
      looking={{ stage: "instruction" }}
      onSeePlan={(target) => setPlanShown(target)}
    >
      <div className="flex min-h-screen flex-col">
        <GalleryHeader
          datasetId={datasetId}
          dataset={dataset.data}
          stage="instruction"
          plan={plan}
        />
        {/* The plan the images are judged by, in the second row as on every screen of the
            dataset (user 2026-10-28). */}
        <PlanBasis
          row
          datasetId={datasetId}
          plan={plan}
          onPlan={(next) =>
            go({ screen: "gallery", datasetId, stage: "instruction", recordId: null, plan: next })
          }
        />
        {active && (
          <div className="border-b border-line bg-sheet px-5 py-2">
            <RunBar run={active} onChanged={reloadAll} />
          </div>
        )}
        <main className="flex flex-col gap-5 px-5 py-4">
          {/* A record named: its samples. Else the work above the plan, the plan now's
              (definition 56). */}
          {recordId ? (
            <TrialView datasetId={datasetId} runId={recordId} imageIds={[]} />
          ) : (
            !earlier && focus
          )}
          {earlier ? (
            // An earlier plan looked at (definition 56): the saved version or the draft's write
            // as it was, read only.
            <PlanScreen
              datasetId={datasetId}
              {...("revision" in earlier
                ? { version: String(earlier.revision) }
                : { write: earlier.write })}
              images={planImages}
              colors={colors}
            />
          ) : (
            state.data && (
              <PlanBook
                datasetId={datasetId}
                state={state.data}
                purpose={dataset.data?.purpose ?? ""}
                base={draft ? (latest.data?.label_definitions ?? null) : null}
                colors={colors}
                images={images}
                folded={Boolean(recordId || focus)}
                asking={asking}
                trial={trialRun}
              />
            )
          )}
          {/* The photos under the plan whatever the right is about, judged by the plan looked
              at (user 2026-10-27). */}
          {state.data && <PlanImages datasetId={datasetId} plan={earlier ?? now} />}
        </main>
      </div>
      <Dialog
        open={planShown !== null}
        onOpenChange={(open) => !open && setPlanShown(null)}
        title={t("work.decision.instruction")}
        wide
      >
        {planShown && (
          <PlanScreen
            datasetId={datasetId}
            {...(planShown.revision !== undefined
              ? { version: String(planShown.revision) }
              : planShown.write !== undefined
                ? { write: planShown.write }
                : draft
                  ? {}
                  : { version: "latest" })}
            images={planImages}
            colors={colors}
          />
        )}
      </Dialog>
    </AgentShell>
  );
}
