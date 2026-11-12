// A worker's proposal answered in its line of the talk (definition 17.1, 18.1): the proposal
// was made in the talk, so it is decided there. The server's card is drawn as a figure (lib/
// cardView, RunCardView: what is used, the record it is compared with by number, counts as
// tags, the use as a table; a worker's own words are only its reason), then the numbered
// options. A run is the same thing as the bar of annotating with AI shows (definition 40.2): the
// images the person changed on the right are its images here too, a heavy one asks once in a
// window before it starts, and once decided its line says how far it is, with stop.
import { useState } from "react";
import { toast } from "sonner";
import type { AgentInfo, Proposal, Run, RunCard } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Confirm } from "@/components/ui/dialog";
import { t, when } from "@/i18n";
import { useModelName } from "@/lib/runChoice";
import { runCardView, runLine } from "@/lib/cardView";
import {
  decideLabel,
  type PlanTarget,
  planToOpen,
  type Said,
  workersAnswering,
} from "@/lib/decisions";
import { errorText } from "@/lib/errorText";
import { applyBox, declineBox } from "@/lib/propose";
import { changesOf, decideRun, runDecisionBody, runImages, useRunPreview } from "@/lib/runDecision";
import { afterOf, withdrawnWhy } from "@/lib/talk";
import { queryClient, useApi } from "@/lib/useApi";
import { dropRunChanges, useRunChanges } from "@/lib/viewState";
import { changedText, runState } from "@/lib/work";
import { NewDatasetFields } from "./NewDatasetFields";
import { RunBar } from "./RunBar";
import { RunCardView } from "./RunCardView";

// The decisions that make a dataset, its name and purpose given with them.
const MAKING = ["dataset_create", "dataset_from"];

export function ProposalReply({
  datasetId,
  box,
  chat,
  onSeeOnRight,
  onRight = false,
  confirming,
  onConfirming,
  onSeePlan,
  onDecided,
}: {
  /** The dataset it is of; none: a decision of the library (definition 22.2). */
  datasetId: string | null;
  box: Proposal;
  /** The chat it is answered in, told what came of it (definition 81). */
  chat: number | null;
  /** Its things on the right (the images it runs, what it changes); none at the library. */
  onSeeOnRight?: (proposalId: string) => void;
  /** The right shows this box already: its links say so, not pressed (definition 37.5). */
  onRight?: boolean;
  /** The heavy decision's window is open (pressed, or "1" typed in the talk). */
  confirming: boolean;
  onConfirming: (open: boolean) => void;
  /** Open the plan a run's proposal runs, its whole text and what changed (Astra 2026-10-17:
   * "2 more" pointed at an operation that was not there). */
  onSeePlan?: (target: PlanTarget, from?: string) => void;
  /** It was decided here (the talk's next place, definition 33.4). */
  onDecided?: (box: Proposal) => void;
}) {
  const agents = useApi<{ agents: AgentInfo[] }>(
    datasetId ? `/v1/datasets/${datasetId}/agents` : null,
  );
  const [busy, setBusy] = useState(false);
  const [opened, setOpened] = useState(false);
  const modelName = useModelName();
  // A run's values as the person changed them on the right (definition 40.2): its figure and
  // its button are of those, read as the bar reads them.
  const run = box.tool === "run_start" && datasetId !== null && box.waiting;
  const [stored] = useRunChanges(datasetId ?? "", run ? box.id : null);
  const changes = run ? stored : {};
  const changed = Object.keys(changes).length > 0;
  const reread = useRunPreview(
    changed ? datasetId : null,
    changed ? runDecisionBody(datasetId ?? "", box, changes, []) : null,
  );
  const preview = changed ? (reread.data?.preview ?? box.preview) : box.preview;
  const card = (preview?.card ?? null) as RunCard | null;
  const names = new Map(
    (Array.isArray(box.preview?.images)
      ? (box.preview.images as { id: string; name: string }[])
      : []
    ).map((i) => [i.id, i.name]),
  );
  const nameOf = (id: string) => names.get(id) ?? id;
  const targets = runImages(box, changes, []);
  // A trial is the plan's (its place, actions.place).
  const trial = box.stage === "instruction";
  const view = card ? runCardView(card, targets, modelName) : null;
  // What deciding does, in the words of its button (lib/decisions).
  const decideWords = t(
    ...decideLabel({ ...box, args: { ...box.args, ...changes }, preview }, nameOf),
  );
  const author = box.agent;
  // A dataset made: its name and purpose as the worker wrote them, changed here before deciding
  // (user 2026-10-29: the reception wrote a purpose nobody said, and it is fixed once made).
  const making = MAKING.includes(box.tool) && box.waiting;
  const [named, setNamed] = useState({
    name: typeof box.args.name === "string" ? box.args.name : "",
    purpose: typeof box.args.purpose === "string" ? box.args.purpose : "",
  });
  const edits = making
    ? Object.fromEntries(Object.entries(named).filter(([key, value]) => value !== box.args[key]))
    : {};
  const unnamed = making && !(named.name.trim() && named.purpose.trim());
  // While a worker answers, its answer may write the plan: no run is decided (11.10).
  const writing = box.tool === "run_start" && workersAnswering(agents.data?.agents ?? []);

  async function act(task: () => Promise<unknown>, done?: string) {
    setBusy(true);
    try {
      await task();
      if (done) toast.success(done);
      onConfirming(false);
    } catch (reason) {
      toast.error(errorText(reason));
    } finally {
      setBusy(false);
      void queryClient.invalidateQueries();
    }
  }
  const decide = () => {
    if (view?.heavy && !confirming) return onConfirming(true);
    void act(async () => {
      if (datasetId && box.tool === "run_start")
        await decideRun(datasetId, box, runDecisionBody(datasetId, box, {}, []), null, chat);
      else await applyBox(box.id, Object.keys(edits).length ? edits : undefined, chat);
      onDecided?.(box);
    }, t("band.decided"));
  };
  const decline = () =>
    void act(async () => {
      await declineBox(box.id, chat);
      if (datasetId) dropRunChanges(datasetId, box.id);
    }, t("band.declined"));
  // Once decided, the run it started: how far it is, with stop (definition 40.2).
  const runs = useApi<{ runs: Run[] }>(
    datasetId && box.tool === "run_start" && box.state === "applied"
      ? `/v1/datasets/${datasetId}/runs`
      : null,
  );
  const started = runs.data?.runs.find((r) => r.id === box.outcome?.id) ?? null;

  const sentence = ([key, values]: Said) =>
    t(key, key === "band.after.model" ? { model: modelName(String(values.model)) } : values);
  // A run is a figure; the other proposals (a version kept, an image in or out) a line of what
  // they do.
  const body = (
    <div className="flex flex-col gap-1.5">
      {view ? (
        <RunCardView
          view={view}
          nameOf={nameOf}
          onSeeImages={onRight ? undefined : () => onSeeOnRight?.(box.id)}
          narrow
        />
      ) : (
        <p className="m-0">
          {afterOf(box)
            .map((line) => t("text.sentence", { text: sentence(line) }))
            .join("")}
        </p>
      )}
      {box.reason && (
        <p className="m-0 text-xs text-muted-foreground">{t("reply.why", { why: box.reason })}</p>
      )}
      {box.preview?.warning === "haiku_accuracy" && (
        <p className="m-0 rounded border border-processing bg-draft px-2 py-1">{t("band.haiku")}</p>
      )}
    </div>
  );
  const links = (
    <span className="flex flex-wrap items-center gap-x-2">
      {/* What goes on the right, in its words there: a trial's images on the plan's screen
          ("Try 3"), an Apply decision's in its band ("the decision's images 4"). */}
      {targets.length > 0 && onSeeOnRight && onRight && (
        <span className="text-xs text-muted-foreground">
          {t(trial ? "reply.onRight.trial" : "reply.onRight.targets", { count: targets.length })}
        </span>
      )}
      {targets.length > 0 && onSeeOnRight && !onRight && (
        <Button variant="link" size="small" onClick={() => onSeeOnRight(box.id)}>
          {t(trial ? "reply.seeRight.trial" : "reply.seeRight.targets", {
            count: targets.length,
          })}
        </Button>
      )}
      {box.tool === "run_start" && onSeePlan && (
        <Button variant="link" size="small" onClick={() => onSeePlan(planToOpen(box), box.id)}>
          {t("record.plan.open")}
        </Button>
      )}
    </span>
  );

  // Decided, declined, withdrawn or failed: a record in one line, as the server's lines are
  // (user 2026-10-27: a framed card looked as if it still waited to be pressed, and the line
  // under it said the same), its contents on asking and, where the right can show it, the way
  // there (said, not pressed, when it is there already).
  if (!box.waiting) {
    // Its facts were taken when it was proposed; only an applied (or failed) one was decided
    // on them (user 2026-10-17: "when decided" stood on boxes never decided).
    const decided = box.decided;
    const changed = changedText(box.changed, modelName);
    return (
      <section
        data-box={box.id}
        aria-label={t("reply.record")}
        className="flex flex-col gap-1 border-l-2 border-line pl-2 text-xs text-muted-foreground"
      >
        <span className="flex flex-wrap items-baseline gap-x-2">
          <b className="text-ink">{t(`work.box.state.${box.state}`)}</b>
          <span className="text-ink">{box.title}</span>
          {changed && <span>{t("work.decision.changedBy", { changes: changed })}</span>}
          {box.state === "withdrawn" && (
            <span>{t("band.withdrawn.why", { why: t(...withdrawnWhy(box.outcome)) })}</span>
          )}
          <Button variant="link" size="small" onClick={() => setOpened(!opened)}>
            {t(
              opened ? "reply.contents.close" : decided ? "reply.contents" : "reply.contents.made",
            )}
          </Button>
          {onSeeOnRight &&
            (onRight ? (
              <span>{t("reply.onRight")}</span>
            ) : (
              <Button variant="link" size="small" onClick={() => onSeeOnRight(box.id)}>
                {t("reply.seeRight")}
              </Button>
            ))}
          <span className="text-note">{when(box.decided_at ?? box.created_at)}</span>
        </span>
        {/* The run it started, as the bar says it: how far, with stop; or how it ended. */}
        {datasetId && started && started.going && (
          <RunBar run={started} onChanged={() => void queryClient.invalidateQueries()} />
        )}
        {/* Ended: how; its record is "see on the right" above. */}
        {datasetId && started && !started.going && (
          <span>
            {t("reply.run.ended", {
              state: t(`run.status.${runState(started.status, started.error_code)}`),
              done: started.succeeded,
              total: started.total,
            })}
          </span>
        )}
        {opened && (
          <div className="flex flex-col gap-1 border-t border-line pt-1 text-body text-ink">
            <span className="text-note text-muted-foreground">
              {t(decided ? "reply.contents.when" : "reply.contents.when.made")}
            </span>
            {body}
          </div>
        )}
      </section>
    );
  }

  return (
    <section
      data-box={box.id}
      aria-label={t("reply.label")}
      className="flex flex-col gap-1.5 rounded-md border-2 border-action bg-surface px-2.5 py-2 text-body"
    >
      <span className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted-foreground">
        <b className="text-ink">{t("reply.head")}</b>
        <span>{when(box.created_at)}</span>
        {view && <span>{t(view.heavy ? "reply.weight.heavy" : "reply.weight.light")}</span>}
      </span>
      <b className="text-lead text-balance">{box.title}</b>
      {/* The worker's title stays its words; what the person changed is said with it. */}
      {changed && (
        <span className="text-body text-muted-foreground">
          {t("work.decision.changedOpen", {
            changes: changedText(changesOf(box, changes), modelName),
          })}
        </span>
      )}
      {body}
      {making && (
        <NewDatasetFields
          name={named.name}
          purpose={named.purpose}
          onName={(name) => setNamed({ ...named, name })}
          onPurpose={(purpose) => setNamed({ ...named, purpose })}
        />
      )}
      {links}
      {/* A heavy one asks once, in a window, as in the bar (definition 40.1). */}
      <Confirm
        open={confirming && Boolean(view?.heavy)}
        title={t("decide.irreversible")}
        // What starts: as the button says it, with the run's line.
        message={view ? `${decideWords}${t("decide.bar.join")}${runLine(view)}` : decideWords}
        confirm={t("decide.start")}
        cancel={t("reply.cancel")}
        onConfirm={decide}
        onCancel={() => onConfirming(false)}
      />
      <ol className="m-0 flex list-none flex-col gap-1 p-0">
        <>
          <li className="flex flex-wrap items-center gap-1.5">
            <span className="w-4 text-right">1.</span>
            <Button
              variant="primary"
              size="small"
              className="h-auto min-h-7 whitespace-normal py-1 text-left"
              disabled={busy || writing || unnamed || Boolean(view?.held)}
              title={writing ? t("decide.writing") : view?.held ? t(...view.held) : undefined}
              onClick={decide}
            >
              {decideWords}
              {view?.heavy ? t("decide.bar.more") : ""}
            </Button>
            {/* Why it cannot be decided now, beside it (Sol 2026-10-17: a tooltip only). */}
            {writing && <span className="text-xs">{t("decide.writing")}</span>}
          </li>
          <li className="flex items-center gap-1.5">
            <span className="w-4 text-right">2.</span>
            <Button size="small" disabled={busy} onClick={decline}>
              {t("band.decline")}
            </Button>
          </li>
          <li className="text-xs text-muted-foreground">
            {t("reply.change", { agent: t(`agent.${author}`) })}
          </li>
        </>
      </ol>
    </section>
  );
}
