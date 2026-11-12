// The workers' buttons at the top of the left (agent app 4.2), inside a dataset and on the
// library (types design 16.2): each with its icon, its name and what waits on the person, a
// number that clears them when pressed (definition 44.3: the reception's every place's, the
// steward's its dataset's). A worker that cannot be chosen here (on the library before any
// dataset was opened) is shown and disabled with why.
import { useState } from "react";
import { toast } from "sonner";
import {
  ArrowLeft,
  ArrowRight,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";
import { api } from "@/api/client";
import type { AgentInfo, AgentKey, TurnPlace, Turns } from "@/api/types";
import { Confirm } from "@/components/ui/dialog";
import { t } from "@/i18n";
import { errorText } from "@/lib/errorText";
import { WORKERS } from "@/lib/home";
import { hasNew, marksOf } from "@/lib/talk";
import { countOf, placesOf } from "@/lib/turns";
import { queryClient, useApi } from "@/lib/useApi";
import { placeKey, useSeenLines, useSideLayout } from "@/lib/viewState";

export function WorkerTabs({
  current,
  datasetId,
  folded,
  right,
  onChoose,
  onUnfold,
  unavailable,
  note,
}: {
  current: AgentKey;
  /** The steward's dataset (the open one, on the library the one opened last; none: none). */
  datasetId: string | null;
  folded: boolean;
  right: boolean;
  onChoose: (agent: AgentKey) => void;
  onUnfold: () => void;
  /** Why a worker cannot be chosen here (none: every one can). */
  unavailable?: (agent: AgentKey) => string | null;
  /** A word under a worker instead of its state (the library: whose workers they are). */
  note?: (agent: AgentKey) => string | null;
}) {
  const [, setLayout] = useSideLayout();
  // Each worker as its own place says (definition 48.6): the reception's the library's, the
  // steward's its dataset's; what was read of each, kept per place.
  const library = useApi<{ agents: AgentInfo[] }>("/v1/library/agents").data;
  const dataset = useApi<{ agents: AgentInfo[] }>(
    datasetId ? `/v1/datasets/${datasetId}/agents` : null,
  ).data;
  const [seenLibrary] = useSeenLines(placeKey(null));
  const [seenDataset] = useSeenLines(placeKey(datasetId));
  const infoOf = (key: AgentKey) =>
    library?.agents.find((a) => a.agent === key && a.place === "library") ??
    dataset?.agents.find((a) => a.agent === key && a.place === "dataset");
  const seenOf = (info: AgentInfo | undefined) =>
    info && (info.place === "library" ? seenLibrary : seenDataset)[info.agent];
  const turns = useApi<Turns>("/v1/turns").data;
  // Whose turns the confirm clears: the library's worker's are every place's, a dataset's
  // worker's its dataset's.
  const [clearing, setClearing] = useState<AgentKey | null>(null);
  const atLibrary = (key: AgentKey) => infoOf(key)?.place === "library";
  const placesFor = (key: AgentKey): TurnPlace[] =>
    atLibrary(key) ? placesOf(turns, null) : datasetId ? placesOf(turns, datasetId) : [];
  const cleared = clearing ? placesFor(clearing) : [];
  async function clearTurns(key: AgentKey) {
    setClearing(null);
    try {
      const done = await api<{ boxes: number; questions: number; trouble: number }>(
        "/v1/turns/clear",
        { body: { dataset_id: atLibrary(key) ? null : datasetId } },
      );
      toast.success(t("turns.clear.done", { count: done.boxes + done.questions + done.trouble }));
    } catch (reason) {
      toast.error(errorText(reason));
    } finally {
      void queryClient.invalidateQueries();
    }
  }
  return (
    // A column per worker and one for the panel's buttons, from the workers there are (it was
    // four columns for three workers and kept a blank one when they became two).
    <div
      role="group"
      aria-label={t("side.workers")}
      style={{ "--workers": WORKERS.length } as React.CSSProperties}
      className={`grid gap-1 border-b border-line p-2 ${folded ? "grid-cols-1 justify-items-center max-[999px]:grid-cols-[repeat(var(--workers),minmax(0,1fr))_auto]" : "grid-cols-[repeat(var(--workers),minmax(0,1fr))_auto]"}`}
    >
      {WORKERS.map((key) => {
        const a = infoOf(key);
        const m = marksOf(a);
        // Lines of its talk not read yet (user 2026-10-15: one may go into a dataset before the
        // reception's answer comes).
        const fresh = key !== current && hasNew(a?.last_event ?? undefined, seenOf(a));
        const places = placesFor(key);
        const count = countOf(places);
        // A dataset's worker's "!": something failed or went out of date in its dataset.
        const trouble = !atLibrary(key) && places.some((p) => p.trouble > 0);
        const why = unavailable?.(key) ?? null;
        const state = why
          ? why
          : note?.(key)
            ? (note(key) as string)
            : atLibrary(key)
              ? t("side.state.all", { count })
              : trouble
                ? t("side.state.trouble")
                : count
                  ? t("side.state.count", { count })
                  : m.working
                    ? t("side.state.working")
                    : fresh
                      ? t("side.new")
                      : t("side.state.idle");
        const label = `${t(`agent.${key}`)} (${t(`agent.does.${key}`)}) ${state}`;
        return (
          <div key={key} className="relative min-w-0">
            <button
              type="button"
              aria-current={key === current ? "true" : undefined}
              aria-label={label}
              title={label}
              disabled={Boolean(why)}
              onClick={() => onChoose(key)}
              className={`flex w-full min-w-0 cursor-pointer flex-col items-center gap-0.5 rounded-lg px-0.5 py-1.5 hover:bg-hover disabled:cursor-default disabled:opacity-50 ${key === current ? "bg-selected" : ""}`}
            >
              <span
                className={`relative grid size-10 place-items-center rounded-[10px] border bg-surface text-heading font-semibold text-action ${key === current ? "border-2 border-action" : "border-line"}`}
              >
                {t(`agent.${key}.icon`)}
                {m.working && (
                  <span className="absolute -right-1.5 -bottom-1.5 size-3 animate-spin rounded-full border-2 border-processing border-t-transparent bg-surface motion-reduce:animate-none" />
                )}
                {fresh && (
                  <span
                    title={t("side.new.title", { agent: t(`agent.${key}`) })}
                    className="absolute -top-1.5 -left-2 z-10 rounded-lg bg-action px-1 text-tiny leading-[15px] font-bold text-white"
                  >
                    {t("side.new")}
                  </span>
                )}
              </span>
              <span
                className={`text-center text-note leading-tight ${key === current ? "font-semibold text-ink" : "text-muted-foreground"}`}
              >
                {t(`agent.${key}`)}
              </span>
              {/* Its main role, small (user 2026-10-13); the library says whose they are. */}
              {!folded && (
                <span className="max-w-full min-w-0 text-center text-tiny leading-tight text-muted-foreground [overflow-wrap:anywhere]">
                  {why ?? note?.(key) ?? <Role text={t(`agent.role.${key}`)} />}
                </span>
              )}
            </button>
            {/* What waits for the person, as a number on the icon's corner (user 2026-10-13: not
              in words under it); pressing it clears them, after a confirm (definition 44.3). */}
            {count > 0 && !why && (
              <button
                type="button"
                aria-label={t("turns.clear.open", { agent: t(`agent.${key}`), count })}
                title={t("turns.clear.open", { agent: t(`agent.${key}`), count })}
                onClick={() => setClearing(key)}
                className={`absolute top-0 left-[calc(50%+10px)] h-[18px] min-w-[18px] cursor-pointer rounded-full px-1 text-center text-note leading-[18px] font-semibold hover:ring-2 hover:ring-ink ${trouble ? "bg-failed text-white" : "bg-processing text-ink"}`}
              >
                {trouble ? "!" : count}
              </button>
            )}
          </div>
        );
      })}
      <Confirm
        open={clearing !== null}
        title={t("turns.clear.title", { count: countOf(cleared) })}
        message={t("turns.clear.how")}
        confirm={t("turns.clear.do")}
        cancel={t("reply.cancel")}
        onConfirm={() => clearing && void clearTurns(clearing)}
        onCancel={() => setClearing(null)}
      >
        {/* Two columns, the counts in line (memory align-and-leave-blank). */}
        <ul className="m-0 grid list-none grid-cols-[max-content_1fr] gap-x-4 gap-y-1 px-5 pb-4">
          {cleared.map((p) => (
            <li key={p.dataset_id ?? "library"} className="contents">
              <b>{p.name ?? t("turns.library")}</b>
              <span className="text-muted-foreground">
                {t("turns.place", { boxes: p.boxes, questions: p.questions, trouble: p.trouble })}
              </span>
            </li>
          ))}
        </ul>
      </Confirm>
      {folded && (
        <button
          type="button"
          aria-label={t("side.unfold")}
          title={t("side.unfold")}
          onClick={onUnfold}
          className="inline-flex size-7 cursor-pointer items-center justify-center rounded-md border border-line bg-surface text-ink hover:bg-hover"
        >
          {right ? <PanelRightOpen className="size-4" /> : <PanelLeftOpen className="size-4" />}
        </button>
      )}
      {/* The panel's own look, beside the workers' row it changes (user 2026-10-13: they were
          in the talk's heading): to the other side, and folding. */}
      {!folded && (
        <div className="flex flex-col items-end gap-1 justify-self-end">
          <button
            type="button"
            aria-label={t(right ? "side.toLeft" : "side.toRight")}
            title={t(right ? "side.toLeft" : "side.toRight")}
            onClick={() => setLayout({ right: !right })}
            className="inline-flex size-7 cursor-pointer items-center justify-center rounded-md border border-line bg-surface text-ink hover:bg-hover max-[999px]:hidden"
          >
            {right ? <ArrowLeft className="size-4" /> : <ArrowRight className="size-4" />}
          </button>
          <button
            type="button"
            aria-label={t("side.fold")}
            title={t("side.fold")}
            onClick={() => setLayout({ folded: true })}
            className="inline-flex size-7 cursor-pointer items-center justify-center rounded-md border border-line bg-surface text-ink hover:bg-hover"
          >
            {right ? <PanelRightClose className="size-4" /> : <PanelLeftClose className="size-4" />}
          </button>
        </div>
      )}
    </div>
  );
}

/** A role in two parts joined by a middle dot breaks only there (user 2026-10-15: the plan's
 * role broke inside its last word); other words wrap as they are. */
const DOT = "\u30fb";
function Role({ text }: { text: string }) {
  const parts = text.split(DOT);
  if (parts.length < 2) return <>{text}</>;
  return (
    <>
      {parts.map((part, index) => (
        <span key={index} className="inline-block">
          {part}
          {index < parts.length - 1 ? DOT : ""}
        </span>
      ))}
    </>
  );
}
