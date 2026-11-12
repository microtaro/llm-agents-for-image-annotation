// One dataset on the library's list: a few of its images, its name and purpose, what its latest
// version puts on the images and how far the annotation came (definition 57), what to do now
// with its worker; its ring while a library decision is being made, and its size and what it
// shares while tidying (user 2026-10-15).
import { Pin } from "lucide-react";
import { toast } from "sonner";
import { api, thumbnailUrl } from "@/api/client";
import type { AgentInfo, AgentKey, DatasetSummary, Progress, Proposal } from "@/api/types";
import { AgentMark } from "@/components/AgentMark";
import { Button } from "@/components/ui/button";
import { ChooseRing } from "@/components/ChooseRing";
import { t, when } from "@/i18n";
import { formatBytes } from "@/lib/bytes";
import { calledName } from "@/lib/library";
import { homeOf } from "@/lib/home";
import { formatRoute, go } from "@/lib/route";
import { errorText } from "@/lib/errorText";
import { turnBoxOf } from "@/lib/talk";
import { useApi } from "@/lib/useApi";
import { enterToTalk, toLineOfBox, useSideLayout } from "@/lib/viewState";
import { NextLine } from "./NextLine";
import { StateBar } from "@/components/StateBar";
import { versionOf } from "@/lib/runChoice";
import { labelsFull, labelsLine } from "@/lib/stateCounts";
import { sourceLines } from "@/lib/sources";

export function DatasetCard({
  dataset,
  chosen,
  ring,
  tidying = false,
  compact = false,
}: {
  dataset: DatasetSummary;
  /** The dataset now (the left's workers are its). */
  chosen: boolean;
  /** Chosen for the library's decision being made (none: no decision, the card opens it). */
  ring?: { chosen: boolean; label: string; onChoose: (on: boolean) => void };
  /** Tidying: its size and the datasets it shares images with (what deleting would keep). */
  tidying?: boolean;
  /** Small, to choose by the images (user 2026-10-29): its images and name only, the rest on
   * hover. */
  compact?: boolean;
}) {
  const progress = useApi<Progress>(`/v1/datasets/${dataset.id}/progress`);
  // The person's turns, per worker, as the left's marks count them (Sol 2026-10-15: the
  // reception named a dataset's turn the card did not show).
  const agents = useApi<{ agents: AgentInfo[] }>(`/v1/datasets/${dataset.id}/agents`);
  // What waits in the dataset, by the worker that made it, whichever its place (the library's
  // worker's box of a dataset waits here too, 48.12).
  const turns = (agents.data?.agents ?? []).filter((a) => a.waiting + a.trouble > 0);
  const [, setLayout] = useSideLayout();
  // To the worker's talk at its place, at its first box's line there (questions and trouble are
  // in its talk).
  async function toTurnOf(agent: AgentKey) {
    enterToTalk(dataset.id);
    try {
      const listed = await api<{ proposals: Proposal[] }>(`/v1/datasets/${dataset.id}/proposals`);
      const box = turnBoxOf(listed.proposals, agent);
      if (box) toLineOfBox(box);
    } catch (reason) {
      toast.error(errorText(reason));
    }
    setLayout({ folded: false });
    go(homeOf(agent, dataset.id));
  }
  // The whole card opens the gallery (the name's link stretched over it); the ring sits above
  // that link, as on the gallery's cards, on every screen (definition 60.2). No menu on each card
  // (user 2026-10-15: the same icon on every card; what is done is the library's screens').
  return (
    <div
      className={`relative flex min-w-0 flex-col rounded-md border bg-sheet text-ink hover:border-action ${compact ? "gap-1.5 p-2.5" : "gap-2.5 px-4.5 py-4"} ${ring?.chosen ? "border-ink ring-2 ring-ink" : "border-line"}`}
    >
      {/* A few of its images, to know it by (user 2026-10-15: choosing where to add by the
          name alone was hard). */}
      <div
        className={`relative grid gap-1 overflow-hidden rounded bg-backdrop ${compact ? "grid-cols-2 [&>img]:aspect-square" : "h-20 grid-cols-4"}`}
      >
        {ring && (
          <ChooseRing
            chosen={ring.chosen}
            label={ring.label}
            use={false}
            done={false}
            onChoose={ring.onChoose}
          />
        )}
        {dataset.thumbnails.map((imageId) => (
          <img
            key={imageId}
            src={thumbnailUrl(imageId, 160)}
            alt=""
            loading="lazy"
            className="size-full object-cover"
          />
        ))}
      </div>
      {/* The name takes the room and wraps in it; the date and the menu stay together at the
          right, and go to a row of their own only on a narrow screen (Sol 2026-10-12: at 320 px
          the menu ran out to the right; then the menu alone fell to a second row on long names). */}
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <span className="flex min-w-0 flex-[1_1_12rem] items-baseline gap-x-2.5">
          {/* The dataset now (the left's workers are its): a mark set by coming in, not a
              button (user 2026-10-14: a pressable ring read as "choose, then come in"). The
              ring is choosing, for the screen's decision. */}
          {chosen && (
            // A pin, not a ring (user 2026-10-16: a ring reads as something to press; a pin says
            // "in use now"), in the "here" blue-green (red is for what cannot be undone).
            <Pin
              role="img"
              aria-label={t("lib.chosen", { name: calledName(dataset) })}
              // A pushpin, as a paper pinned (user 2026-10-16: not a map's pin), its head filled.
              className="size-5 shrink-0 self-center rotate-[30deg] fill-here text-here"
              strokeWidth={2}
            >
              <title>{t("lib.chosen", { name: calledName(dataset) })}</title>
            </Pin>
          )}
          <a
            href={formatRoute({
              screen: "gallery",
              datasetId: dataset.id,
              stage: null,
              recordId: null,
            })}
            // Coming in from the library: the steward, at the stage now (definition 35.2).
            onClick={() => enterToTalk(dataset.id)}
            title={[
              ...(compact
                ? [
                    t("common.images", { count: dataset.image_count }),
                    t("dataset.purpose", { purpose: dataset.purpose }),
                  ]
                : []),
              ...sourceLines(dataset.sources),
            ].join("\n")}
            // Small, two lines of the name at most, the cards in even rows.
            className={`min-w-0 font-semibold text-ink no-underline [overflow-wrap:anywhere] after:absolute after:inset-0 ${compact ? "line-clamp-2 text-body" : "text-base"}`}
          >
            {/* Its number first, what people call it by (user 2026-10-28, definition 61). */}
            <span className="mr-1.5 font-normal text-muted-foreground tabular-nums">
              {t("dataset.number", { number: String(dataset.number) })}
            </span>
            {dataset.name}
          </a>
          {!compact && (
            <span className="shrink-0 text-muted-foreground">
              {t("common.images", { count: dataset.image_count })}
            </span>
          )}
        </span>
        {!compact && (
          <span className="ml-auto shrink-0 text-xs text-muted-foreground">
            {t("card.lastAt", { time: when(dataset.last_at) })}
          </span>
        )}
      </div>
      {tidying && <TidyLine dataset={dataset} />}
      {!compact && (
        <CardDetails dataset={dataset} progress={progress.data} turns={turns} onTurn={toTurnOf} />
      )}
    </div>
  );
}

/** What one using the dataset needs, under its name on a card big enough for it. */
function CardDetails({
  dataset,
  progress,
  turns,
  onTurn,
}: {
  dataset: DatasetSummary;
  progress: Progress | null;
  turns: AgentInfo[];
  onTurn: (agent: AgentKey) => Promise<void>;
}) {
  return (
    <>
      {/* What one using the dataset needs (definition 57, user 2026-10-27: the card said too
          little): its purpose, what its latest version puts on the images, and how far the
          annotation came at a glance, the parts in words on hover (memory less-at-once). Where
          the images came from is a touch away on the name. */}
      <p className="m-0 text-body text-muted-foreground [overflow-wrap:anywhere]">
        {t("dataset.purpose", { purpose: dataset.purpose })}
      </p>
      {dataset.latest_revision !== null && dataset.labels.length > 0 && (
        <div className="flex flex-col gap-1 text-body">
          <span className="flex min-w-0 items-baseline gap-2" title={labelsFull(dataset.labels)}>
            <b className="shrink-0">{versionOf(dataset.latest_revision)}</b>
            <span className="min-w-0 truncate text-muted-foreground">
              {labelsLine(dataset.labels)}
            </span>
          </span>
          {progress?.facts.counts && (
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <StateBar counts={progress.facts.counts} kind="annotation" />
              <span className="text-small text-muted-foreground">
                {t("card.used", { count: progress.facts.counts.used })}
              </span>
            </span>
          )}
        </div>
      )}
      {turns.length > 0 && (
        <div className="relative z-10 flex flex-wrap items-center gap-x-2 gap-y-1 text-body">
          <span className="font-semibold text-processing-ink">{t("lib.turns")}</span>
          {turns.map((a) => (
            <Button
              key={a.agent}
              size="small"
              variant="link"
              // The words underlined, not the mark (a link's underline ran under it too).
              className="gap-1 no-underline"
              title={t("lib.turns.title", {
                agent: t(`agent.${a.agent}`),
                boxes: a.boxes,
                questions: a.questions,
                trouble: a.trouble,
              })}
              onClick={() => void onTurn(a.agent)}
            >
              <AgentMark agent={a.agent} />
              <span className="underline underline-offset-2">
                {t("lib.turns.count", { count: a.waiting + a.trouble })}
              </span>
            </Button>
          ))}
        </div>
      )}
      <NextLine datasetId={dataset.id} progress={progress} />
    </>
  );
}

/** Its size and what it shares (tidying only): deleting it frees what no other dataset uses.
 * Two names at most, the rest a touch away (memory less-at-once: eight names filled the card). */
function TidyLine({ dataset }: { dataset: DatasetSummary }) {
  const item = (s: DatasetSummary["shared"][number]) =>
    t("library.shared.item", { name: s.name, count: s.images, size: formatBytes(s.bytes) });
  const first = dataset.shared.slice(0, 2).map(item);
  const more = dataset.shared.length - first.length;
  return (
    <p className="m-0 flex flex-wrap gap-x-3 text-body">
      <span>
        {t("library.size", { count: dataset.image_count, size: formatBytes(dataset.bytes) })}
      </span>
      <span
        className="text-muted-foreground"
        title={more ? dataset.shared.map(item).join("\n") : undefined}
      >
        {dataset.shared.length
          ? t("library.shared", {
              list: [...first, ...(more ? [t("library.shared.more", { count: more })] : [])].join(
                t("box.plan.separator"),
              ),
            })
          : t("library.shared.none")}
      </span>
    </p>
  );
}
