// The band on the right (docs/2026-10-09-agent-app-design.md 4.3, definition 18.2): which worker's
// proposal the right shows the things of (its images, the plan it runs), only when the person
// asked for it from the talk, the list of decisions or the library's turns. It is answered in
// its line on the left, where it was made (definition 17.1): the band leads there. A decided
// box is shown with what became of it (DecidedBand).
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import type { AgentKey, Proposal, StageName } from "@/api/types";
import { AgentMark } from "@/components/AgentMark";
import { PERSON } from "@/lib/actors";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { t, when } from "@/i18n";
import { useModelName } from "@/lib/runChoice";
import { type PlanTarget, planToOpen } from "@/lib/decisions";
import { errorText } from "@/lib/errorText";
import { seenBox } from "@/lib/propose";
import { stepOfBox } from "@/lib/stageSteps";
import { afterOf, boxesOn, targetsOf, withdrawnWhy } from "@/lib/talk";
import { invalidate } from "@/lib/useApi";
import {
  setAskDraft,
  toLineOfBox,
  useBandAt,
  useLater,
  useShownOnRight,
  useViewedBox,
} from "@/lib/viewState";
import { WorkDecision } from "./WorkDecision";

/** The band a box is shown in on the gallery: its stage and the step of the row it is at. */
export function boxPlace(proposal: Proposal): string | null {
  return proposal.stage
    ? `${proposal.stage}:${stepOfBox(proposal.stage, proposal.step) ?? ""}`
    : null;
}

/** Show a box in a band (unfolded), from anywhere in the dataset: in its step's (the
 * gallery's), or in the band of an image it is about (the loupe's). */
export function useShowBox(datasetId: string) {
  const [later, setLater] = useLater(datasetId);
  const [at, setAt] = useBandAt(datasetId);
  const [shown, setShown] = useShownOnRight(datasetId);
  return (proposal: Proposal, place: string | null = boxPlace(proposal)) => {
    if (place) setAt({ ...at, [place]: proposal.id });
    setLater(later.filter((x) => x !== proposal.id));
    if (!shown.includes(proposal.id)) setShown([...shown, proposal.id]);
  };
}

/** The box a person asked to see (from the talk): its band, when it is drawn, is brought into
 * view (Sol 2026-10-17: it came at the top while the page was scrolled down, nothing seemed
 * to happen). Only the person's asking, not a box that comes by itself. */
const asked: { id: string | null } = { id: null };

/** The person pressed to see this box: its band is brought into view when drawn. */
export function askToSee(id: string) {
  asked.id = id;
}

function useBroughtIntoView(id: string | null | undefined) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (id && asked.id === id) {
      // The middle, not the top: the sticky bars cover the top of the page.
      ref.current?.scrollIntoView({ block: "center", behavior: "smooth" });
      asked.id = null;
    }
  }, [id]);
  return ref;
}

/** The boxes waiting about one image, oldest first (the loupe's band). */
export function boxesAbout(proposals: Proposal[], imageId: string): Proposal[] {
  return (["instruction", "inspection", "production"] as StageName[])
    .flatMap((stage) => boxesOn(proposals, stage))
    .filter((p) => targetsOf(p).includes(imageId));
}

/** A band: the box shown of those waiting at a place (a stage, or an image as `image:<id>`),
 * null when none waits; whether it is folded ("later"). */
export function useBand(datasetId: string, place: string, boxes: Proposal[]) {
  const [later, setLater] = useLater(datasetId);
  const [at, setAt] = useBandAt(datasetId);
  const index = Math.max(
    0,
    boxes.findIndex((p) => p.id === at[place]),
  );
  const box = boxes[index] ?? null;
  return {
    box,
    index,
    count: boxes.length,
    folded: Boolean(box && later.includes(box.id)),
    step: (by: number) => {
      const next = boxes[(index + by + boxes.length) % boxes.length];
      if (next) setAt({ ...at, [place]: next.id });
    },
    fold: (on: boolean) =>
      box && setLater(on ? [...later, box.id] : later.filter((x) => x !== box.id)),
  };
}

export type Band = ReturnType<typeof useBand>;

export function DecisionBand({
  datasetId,
  band,
  talking,
  onTalk,
  onSeePlan,
  className = "",
  // Wide only: on a narrow screen it covered what was below (Sol 2026-10-09).
  sticky = "min-[1000px]:sticky min-[1000px]:top-(--stage-bar) min-[1000px]:z-10",
}: {
  datasetId: string;
  className?: string;
  /** Where it stays while the page scrolls (the gallery's: below the map). */
  sticky?: string;
  band: Band;
  /** The worker talked with on the left. */
  talking: AgentKey;
  onTalk: (agent: AgentKey) => void;
  /** An image's name (kept for the callers). */
  nameOf?: (imageId: string) => string | undefined;
  /** Open the plan a run's box runs (Sol 2026-10-17: a first run said only "first", its plan
   * was read elsewhere). */
  onSeePlan?: (target: PlanTarget, from?: string) => void;
}) {
  const box = band.box;
  const shownRef = useBroughtIntoView(box?.id);
  const [shown, setShown] = useShownOnRight(datasetId);
  if (!box) return null;
  const author = box.agent;
  const pager = band.count > 1 && (
    <span className="inline-flex items-center gap-1 text-xs">
      <button
        type="button"
        aria-label={t("band.prev")}
        onClick={() => band.step(-1)}
        className="cursor-pointer rounded border border-line bg-surface px-1.5"
      >
        ‹
      </button>
      <button
        type="button"
        aria-label={t("band.next")}
        onClick={() => band.step(1)}
        className="cursor-pointer rounded border border-line bg-surface px-1.5"
      >
        ›
      </button>
      <span>{t("band.position", { at: band.index + 1, count: band.count })}</span>
    </span>
  );
  // What the right shows is a worker's proposal's things; it is answered in its line on the
  // left, where it was made (definition 17.1, 18.2): no decide button here.
  return (
    <section
      ref={shownRef}
      aria-label={t("band.viewing")}
      className={`${sticky} flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border-2 bg-surface px-3.5 py-2 shadow-sm border-action ${className}`}
    >
      {pager}
      <span className="text-xs text-muted-foreground">{t("band.viewing")}</span>
      <b className="min-w-0 flex-1 text-balance">{box.title}</b>
      <span className="text-xs text-muted-foreground">
        <From madeBy={box.made_by} author={author} /> · {when(box.created_at)}
      </span>
      {box.tool === "run_start" && onSeePlan && (
        <Button variant="link" size="small" onClick={() => onSeePlan(planToOpen(box), box.id)}>
          {t("record.plan.open")}
        </Button>
      )}
      <Button
        variant="primary"
        size="small"
        onClick={() => {
          toLineOfBox(box);
          if (author !== talking) onTalk(author);
        }}
      >
        {t("band.answerLeft")}
      </Button>
      <Button size="small" onClick={() => setShown(shown.filter((id) => id !== box.id))}>
        {t("common.close")}
      </Button>
    </section>
  );
}

/** A decided box, shown from the talk: what became of it, what it was, Details, Close. */
export function DecidedBand({
  datasetId,
  proposal,
  onTalk,
  className = "",
}: {
  datasetId: string;
  proposal: Proposal;
  /** The worker talked with on the left (kept for the callers; "ask" goes to the author). */
  talking: AgentKey;
  onTalk: (agent: AgentKey) => void;
  className?: string;
}) {
  const [, setViewed] = useViewedBox(datasetId);
  const [details, setDetails] = useState(false);
  const shownRef = useBroughtIntoView(proposal.id);
  const author = proposal.agent;
  const named = useModelName();
  const modelName = (model: string | number) => named(String(model));
  return (
    <section
      ref={shownRef}
      aria-label={t("band.decidedLabel")}
      className={`flex flex-col gap-1 rounded-lg border border-line bg-sheet px-3.5 py-2.5 ${className}`}
    >
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground">
        <b className="text-ink">{t(`work.box.state.${proposal.state}`)}</b>
        <span>
          <From madeBy={proposal.made_by} author={author} /> ·{" "}
          {when(proposal.decided_at ?? proposal.created_at)}
        </span>
        <ConsultButton
          datasetId={datasetId}
          author={author}
          title={proposal.title}
          onTalk={onTalk}
        />
        <span className="flex-1" />
        <Button size="small" onClick={() => setViewed(null)}>
          {t("common.close")}
        </Button>
      </div>
      <div className="text-base font-semibold text-balance">{proposal.title}</div>
      {proposal.reason && (
        <div className="text-body text-muted-foreground">
          {t("band.why", { why: proposal.reason })}
        </div>
      )}
      {proposal.state === "withdrawn" && (
        <div className="text-body">
          {t("band.withdrawn.why", { why: t(...withdrawnWhy(proposal.outcome)) })}
        </div>
      )}
      <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-body">
        {/* What it held (not "after": it may have been declined). */}
        <span className="text-muted-foreground">
          {t(proposal.decided ? "band.contents" : "band.contents.made")}
        </span>
        {afterOf(proposal).map(([key, values]) => (
          <span key={key}>
            {t(key, key === "band.after.model" ? { model: modelName(values.model) } : values)}
          </span>
        ))}
        <Button variant="link" size="small" onClick={() => setDetails(true)}>
          {t("band.detailsOnly")}
        </Button>
      </div>
      <Dialog open={details} onOpenChange={setDetails} title={t("band.detailsOnly")} wide>
        <WorkDecision
          proposal={proposal}
          // The same close as in its line (it did nothing here before; 2026-10-17).
          onSeen={() =>
            void seenBox(proposal.id)
              .then(() => {
                setDetails(false);
                invalidate(datasetId);
              })
              .catch((reason) => toast.error(errorText(reason)))
          }
          onRedo={() => onTalk(author)}
        />
      </Dialog>
    </section>
  );
}

/** "Ask about this decision": the talk with the worker that made it, with the words begun (not
 * sent; types design 16.3.1). */
function ConsultButton({
  datasetId,
  author,
  title,
  onTalk,
}: {
  datasetId: string;
  author: AgentKey;
  title: string;
  onTalk: (agent: AgentKey) => void;
}) {
  return (
    <Button
      variant="link"
      size="small"
      className="gap-1 no-underline"
      title={t("decision.consult.title", { agent: t(`agent.${author}`), title })}
      onClick={() => {
        setAskDraft(datasetId, author, t("decision.consult.text", { title }));
        onTalk(author);
      }}
    >
      <AgentMark agent={author} />
      <span className="underline underline-offset-2">{t("decision.consult")}</span>
    </Button>
  );
}

/** Where a box is from: the person's own press, or the worker that made it by its mark (user
 * 2026-10-15: the right names a worker by its mark; Sol: the worker's name in words beside the
 * consult button with its mark). */
function From({ madeBy, author }: { madeBy: string; author: AgentKey }) {
  if (madeBy === PERSON) return <>{t("band.fromYou")}</>;
  return (
    <span className="inline-flex items-center gap-1 align-middle">
      <AgentMark agent={author} />
      {t("band.fromMark")}
    </span>
  );
}
