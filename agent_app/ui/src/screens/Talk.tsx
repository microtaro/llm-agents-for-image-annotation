// The talk with a worker in its place (definition 48.6), every worker's alike: the steward in a
// dataset, the reception at the library. Its chats (new, history, delete), its lines (each by
// WorkEvent), the unread divider and the chat that has unread lines, a line asked to be shown,
// the answer going (what the worker is doing now, stop), the field, and a number alone answering
// a question or a box. How the right follows the talk is the place's (TalkRight); the right never
// changes the left, and what it shows goes with the words (looking).
import { type ReactNode, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import type {
  AgentChat,
  AgentEvent,
  AgentInfo,
  AgentKey,
  DatasetSummary,
  JobList,
  Proposal,
  QuestionOption,
  Shown,
} from "@/api/types";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { calledName } from "@/lib/library";
import { typedChoice } from "@/lib/cardView";
import type { PlanTarget } from "@/lib/decisions";
import { answeringJobs, answeringSince, doingWords, secondsSince, useNow } from "@/lib/elapsed";
import { errorText } from "@/lib/errorText";
import { waitText } from "@/lib/work";
import { applyBox, declineBox } from "@/lib/propose";
import { decideRun, runDecisionBody } from "@/lib/runDecision";
import {
  focusAsk,
  hasNew,
  historyWords,
  type LookingAt,
  marksOf,
  optionWords,
  runEndCarded,
  toldByCard,
  turnBoxOf,
} from "@/lib/talk";
import { queryClient, useApi } from "@/lib/useApi";
import {
  dropRunChanges,
  placeKey,
  toLineOfBox,
  useAskDrafts,
  useChatOf,
  useLineToShow,
  useSeenLines,
  useSideLayout,
} from "@/lib/viewState";
import { AskForm } from "./AskForm";
import { ChatList } from "./ChatList";
import { ProposalReply } from "./ProposalReply";
import { WorkEvent } from "./WorkEvent";

/** How a place's right follows its talk: a dataset's moves within it, the library's opens a
 * dataset. Every way the talk moves the right goes through these. */
export interface TalkRight {
  /** The right goes to what the newest of these lines points at. asked: the person pressed (a
   * question answered); else new lines of the talk, where the place lets them move it. */
  follow: (lines: AgentEvent[], asked: boolean) => void;
  /** A box's things on the right (its "see"; none: a box of the library). */
  seeBox?: (id: string) => void;
  /** The set a line showed, on the right. */
  seeShown?: (shown: Shown, line: AgentEvent) => void;
  /** Whether the right shows a box, or what a line showed, already (its link says so). */
  boxOnRight: (id: string) => boolean;
  shownOnRight: (line: AgentEvent) => boolean;
  /** A server's line with a place on the right and no box (a run ended, a request handed to the
   * library): whether the right shows it already; null: none. Its "see" goes there. */
  noteOnRight?: (line: AgentEvent) => boolean | null;
  seeNote?: (line: AgentEvent) => void;
  /** A box decided in the talk: its place. */
  decided?: (box: Proposal) => void;
  /** A place an open line names (the library's worker). */
  open?: (place: Record<string, unknown>) => void;
  /** Talk with the steward of a dataset (a request handed there). */
  go?: (datasetId: string) => void;
  /** Open the plan a run's box runs. */
  seePlan?: (target: PlanTarget, from?: string) => void;
}

export function Talk({
  place,
  agent,
  looking,
  scope,
  right,
}: {
  /** The worker's place: a dataset's id, or the library (null). */
  place: string | null;
  agent: AgentKey;
  /** What the person looks at on the right, sent with the words. */
  looking?: LookingAt;
  /** What the right shows, in words (the field says where the words go with). */
  scope: string;
  right: TalkRight;
}) {
  const key = placeKey(place);
  const base = place ? `/v1/datasets/${place}` : "/v1/library";
  const [layout] = useSideLayout();
  const [seen, setSeen] = useSeenLines(key);
  const agents = useApi<{ agents: AgentInfo[] }>(`${base}/agents`);
  const info = agents.data?.agents.find((a) => a.agent === agent);
  // The chat talked in (none chosen: the worker's latest) and the worker's history.
  const [chatOf, setChat] = useChatOf(key);
  const chosen = chatOf[agent];
  const events = useApi<{ events: AgentEvent[]; answering: boolean; chat_id: number }>(
    `${base}/agents/${agent}/events${chosen ? `?chat=${chosen}` : ""}`,
  );
  const chats = useApi<{ chats: AgentChat[] }>(`${base}/agents/${agent}/chats`);
  const chat = events.data?.chat_id ?? null;
  const lines = events.data?.events ?? [];
  const answering = Boolean(events.data?.answering);
  // This chat's answers going or waiting (a request's job is of the chat its line is in).
  const jobs = useApi<JobList>(answering ? "/v1/jobs" : null);
  const lineIds = new Set(lines.map((e) => e.id));
  const going = answeringJobs(jobs.data?.jobs ?? [], agent, lineIds);
  // Since when this answer was asked for, counted on while it goes (definition 33.1).
  const asked = answeringSince(jobs.data?.jobs ?? [], agent, lineIds);
  const nowMs = useNow(answering);
  const [history, setHistory] = useState(false);
  // The library's lines name datasets: by number and name (definition 61), a deleted one said so
  // (Sol 2026-10-15).
  const datasets = useApi<{ datasets: DatasetSummary[] }>(place ? null : "/v1/datasets");
  const nameOf = place
    ? undefined
    : (id: string) => {
        const found = datasets.data?.datasets.find((d) => d.id === id);
        return found ? calledName(found) : datasets.data ? null : id;
      };
  const proposals = useApi<{ proposals: Proposal[] }>(`${base}/proposals`);
  const boxOf = (id: string) => proposals.data?.proposals.find((p) => p.id === id);
  // What a person is writing, per worker (Sol 2026-10-08: words written to one went to the
  // other after choosing it).
  const [drafts, setDraft] = useAskDrafts(key);
  const text = drafts[agent] ?? "";
  const setText = (next: string) => setDraft(agent, next);
  // A proposal is answered in the first line it is in (definition 18.1); a later line pointing
  // at it leads to it.
  const firstLine = new Map<string, number>();
  for (const line of lines) {
    const ids = Array.isArray(line.data?.proposal_ids) ? (line.data.proposal_ids as string[]) : [];
    for (const id of ids) if (!firstLine.has(id)) firstLine.set(id, line.id);
  }
  const waitingHere = [...firstLine.keys()]
    .map((id) => boxOf(id))
    .filter((box): box is Proposal => Boolean(box && box.waiting));
  // The heavy decision whose check is open in its line ("1" typed, or pressed once).
  const [confirmId, setConfirmId] = useState<string | null>(null);

  // While the worker works or answers, everything shown is read again by the one watch of the
  // line of work (lib/workWatch).

  // Where the unread lines begin, as the talk is opened (user 2026-10-15: open at the first
  // unread line with a divider, as chat apps do). Taken before the lines are marked seen below.
  const [unreadFrom, setUnreadFrom] = useState<number | null>(null);
  useEffect(() => {
    setUnreadFrom(seen[agent] ?? null);
    // Only on opening another worker or place.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent, key]);
  // Unread lines in another chat than the one shown (a run ended for a request of an earlier
  // chat): that chat is opened, once on opening the worker (user 2026-10-15).
  const movedFor = useRef<string | null>(null);
  useEffect(() => {
    if (unreadFrom === null || !info || !events.data) return;
    const opened = `${key}:${agent}:${unreadFrom}`;
    if (movedFor.current === opened) return;
    movedFor.current = opened;
    const other = info.last_event_chat;
    if (hasNew(info.last_event ?? undefined, unreadFrom) && other && other !== events.data.chat_id)
      setChat(agent, other);
  }, [unreadFrom, agent, info, events.data, key, setChat]);
  // The lines shown: a box's outcome is said by its card when the card is in this talk.
  const shownLines = lines.filter((e) => !toldByCard(e, firstLine));
  const firstUnread =
    unreadFrom === null
      ? undefined
      : shownLines.find((e) => e.id > unreadFrom && e.kind !== "human");
  // The lines of the worker talked with are seen while its talk is open.
  const last = info?.last_event ?? undefined;
  useEffect(() => {
    if (!layout.folded && last !== undefined && hasNew(last, seen[agent])) setSeen(agent, last);
  });

  // Opened at one line (a version's asking words, a box's line): brought into view and marked
  // for a moment (user 2026-10-14: the end showed, as if nothing had opened).
  const [lineToShow, setLineToShow] = useLineToShow(key);
  const shownHere = useRef<string | null>(null);
  useEffect(() => {
    if (!lineToShow || !events.data || shownHere.current === lineToShow) return;
    const line = document.querySelector<HTMLElement>(
      lineToShow.startsWith("box:")
        ? `[data-box="${CSS.escape(lineToShow.slice(4))}"]`
        : `[data-line="${CSS.escape(lineToShow)}"]`,
    );
    if (!line) return;
    shownHere.current = lineToShow;
    line.scrollIntoView({ block: "center" });
    line.classList.add("ring-4", "ring-processing");
    window.setTimeout(() => {
      line.classList.remove("ring-4", "ring-processing");
      shownHere.current = null;
      setLineToShow(null);
    }, 4000);
  }, [lineToShow, events.data, setLineToShow]);
  const end = useRef<HTMLLIElement>(null);
  const lastLine = lines.at(-1)?.id;
  // Opened with unread lines: at the first of them, once; afterwards a new line goes to the end.
  const openedAt = useRef<string | null>(null);
  // Braces: scrollIntoView returns a promise in Chrome now, which React would take for the
  // effect's cleanup (found 2026-10-08: the screen stayed blank).
  useEffect(() => {
    if (lineToShow || !events.data) return;
    const at = `${agent}:${events.data.chat_id}`;
    if (openedAt.current !== at && firstUnread) {
      openedAt.current = at;
      document.querySelector(`[data-line="${firstUnread.id}"]`)?.scrollIntoView({ block: "start" });
      return;
    }
    openedAt.current = at;
    end.current?.scrollIntoView({ block: "nearest" });
    // The line to show decides on its own; only a new line or worker moves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastLine, agent, events.data?.chat_id]);

  // New lines of the talk move the right, as the place lets them; never on opening the talk or
  // another chat (the right is as it was).
  const followed = useRef<{ chat: number; line: number } | null>(null);
  useEffect(() => {
    const data = events.data;
    if (!data) return;
    const newest = data.events.at(-1)?.id ?? 0;
    const before = followed.current;
    followed.current = { chat: data.chat_id, line: newest };
    if (!before || before.chat !== data.chat_id) return;
    const fresh = data.events.filter((e) => e.id > before.line && e.kind !== "human");
    if (fresh.length) right.follow(fresh, false);
    // Only new lines move it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events.data]);

  async function act(task: () => Promise<unknown>, done?: string) {
    try {
      await task();
      if (done) toast.success(done);
    } catch (reason) {
      toast.error(errorText(reason));
    } finally {
      void queryClient.invalidateQueries();
    }
  }
  const toBox = (id: string) =>
    document.querySelector(`[data-box="${CSS.escape(id)}"]`)?.scrollIntoView({ block: "center" });
  // A question's option chosen (definitions 26.4, 33.3, 34.2, 48.5): the server writes its plan
  // (a dataset's) as the person's and sends its words, as shown here, on.
  const answer = (event: AgentEvent, option: number) => {
    // The right shows what the question is about at once, not after the answer.
    right.follow([event], true);
    const chosenOption = (event.data?.options as QuestionOption[] | undefined)?.[option];
    void act(() =>
      api(`${base}/agents/${agent}/events/${event.id}/answer`, {
        body: { option, ...(chosenOption ? { words: optionWords(chosenOption) } : {}) },
      }),
    );
  };
  // "Other", after the options (34.3): the person writes it in the field.
  const other = focusAsk;
  // A number alone answers the talk's newest line when it is an open question (the server's own
  // lines after it do not count), as pressing its option does; "1" or "2" alone answers the
  // newest waiting proposal otherwise.
  const answered = (words: string): boolean => {
    const newest = lines.filter((e) => e.kind !== "note").at(-1);
    const number = /^\s*([1-4])\s*$/.exec(words.normalize("NFKC"));
    const options = Array.isArray(newest?.data?.options) ? newest.data.options.length : 0;
    if (newest?.kind === "question" && !newest.closed_at && number && options) {
      if (Number(number[1]) === options + 1) {
        setText("");
        other();
        return true;
      }
      if (Number(number[1]) <= options) {
        setText("");
        answer(newest, Number(number[1]) - 1);
        return true;
      }
    }
    const choice = typedChoice(words);
    const box = waitingHere.at(-1);
    if (!choice || !box) return false;
    setText("");
    toBox(box.id);
    const heavy = (box.preview?.card as { weight?: string } | undefined)?.weight === "heavy";
    if (choice === 1 && heavy && confirmId !== box.id) {
      setConfirmId(box.id);
      return true;
    }
    setConfirmId(null);
    // A run with what the person changed on the right (definition 40.2), else the box as it is.
    const decide = () =>
      box.tool === "run_start" && box.dataset_id
        ? decideRun(box.dataset_id, box, runDecisionBody(box.dataset_id, box, {}, []), null, chat)
        : applyBox(box.id, undefined, chat);
    void act(
      () =>
        choice === 1
          ? decide().then(() => right.decided?.(box))
          : declineBox(box.id, chat).then(
              () => box.dataset_id && dropRunChanges(box.dataset_id, box.id),
            ),
      t(choice === 1 ? "band.decided" : "band.declined"),
    );
    return true;
  };
  const send = (words: string) => {
    if (answered(words)) return;
    void act(async () => {
      await api(`${base}/agents/${agent}/messages`, {
        body: { text: words, chat_id: chat, ...(looking ? { looking_at: looking } : {}) },
      });
      setText("");
    });
  };
  const name = t(`agent.${agent}`);
  const marks = marksOf(info);
  // The worker's first decision waiting for the person (or failed and not seen), of any place
  // (the library's worker's box of a dataset is in its talk, 48.12).
  const mine = turnBoxOf(proposals.data?.proposals ?? [], agent);

  return (
    <section aria-label={name} className="flex min-h-0 flex-1 flex-col bg-surface">
      {/* Two rows: who it is, then its operations (one row squeezed the title to a letter per
          line once the chat buttons came, 10-09). */}
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line px-3 py-2">
        <span className="flex min-w-0 basis-full flex-col">
          <b className="text-heading">{name}</b>
          <span className="text-xs text-muted-foreground">{t(`agent.does.${agent}`)}</span>
          {(mine || marks.working) && (
            <span className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
              {/* The count is on the icon (user 2026-10-13); here what it is working on. */}
              {marks.working ? t("side.state.working") : ""}
              {/* What waits is a decision, not a line of the talk (Sol 2026-10-13: "your turn
                  1" with nothing in the talk): one press shows its line. */}
              {mine && (
                <Button variant="link" size="small" onClick={() => toLineOfBox(mine)}>
                  {t("side.state.see")}
                </Button>
              )}
            </span>
          )}
        </span>
        {/* Chats as in any chat app (user 2026-10-09): a new one, the history. */}
        <Button
          size="small"
          onClick={() =>
            void act(async () => {
              const made = await api<{ id: number }>(`${base}/agents/${agent}/chats`, {
                body: {},
              });
              setChat(agent, made.id);
              setHistory(false);
            })
          }
        >
          {t("side.chat.new")}
        </Button>
        <Button size="small" aria-expanded={history} onClick={() => setHistory(!history)}>
          {historyWords(chats.data?.chats ?? [], chat)}
        </Button>
      </header>
      {history && (
        <ChatList
          chats={chats.data?.chats ?? []}
          current={chat}
          onOpen={(id) => {
            setChat(agent, id);
            setHistory(false);
          }}
          onDelete={(id) =>
            void act(async () => {
              await api(`${base}/agents/${agent}/chats/${id}`, { method: "DELETE" });
              if (id === chat) setChat(agent, null);
            }, t("side.chat.deleted"))
          }
        />
      )}
      <ol
        aria-label={t("work.conversation")}
        className="m-0 flex min-h-[160px] flex-1 list-none flex-col gap-2 overflow-y-auto px-3 py-2.5"
      >
        {/* What can be done here, shown first each time (not a line of the talk). */}
        <li className="rounded-md border border-dashed border-line px-2.5 py-1.5 text-body text-muted-foreground">
          {t(`agent.intro.${agent}`)}
        </li>
        {shownLines.map((event) => [
          event.id === firstUnread?.id && (
            <li
              key={`unread-${event.id}`}
              role="separator"
              className="flex items-center gap-2 text-xs font-semibold text-action"
            >
              <span className="h-px flex-1 bg-action" />
              {t("side.unreadFrom")}
              <span className="h-px flex-1 bg-action" />
            </li>
          ),
          <WorkEvent
            key={event.id}
            event={event}
            onSee={right.seeBox}
            boxOnRight={right.boxOnRight}
            showOnRight={right.shownOnRight(event)}
            noteOnRight={
              event.kind === "note" && !runEndCarded(event, firstLine, boxOf)
                ? (right.noteOnRight?.(event) ?? null)
                : null
            }
            onSeeNote={right.seeNote ? () => right.seeNote?.(event) : undefined}
            onAnswer={answer}
            onOther={other}
            boxOf={boxOf}
            nameOf={nameOf}
            onOpen={right.open}
            onGo={right.go}
            reply={(id, lineId) => {
              const box = boxOf(id);
              if (!box || firstLine.get(id) !== lineId) return null;
              return (
                <ProposalReply
                  key={id}
                  datasetId={box.dataset_id}
                  box={box}
                  chat={chat}
                  onSeeOnRight={box.dataset_id ? right.seeBox : undefined}
                  onRight={right.boxOnRight(id)}
                  onSeePlan={right.seePlan}
                  onDecided={right.decided}
                  confirming={confirmId === id}
                  onConfirming={(open) => setConfirmId(open ? id : null)}
                />
              );
            }}
            onShow={right.seeShown ? (shown) => right.seeShown?.(shown, event) : undefined}
            onHand={(e) =>
              void act(async () => {
                const handed = await api<{ dataset_id: string | null }>(
                  `${base}/agents/${agent}/handoffs`,
                  { body: { event_id: e.id } },
                );
                if (handed.dataset_id) right.go?.(handed.dataset_id);
              }, t("work.handoff.sent"))
            }
            onClose={(e) =>
              void act(() => api(`${base}/agents/${agent}/events/${e.id}/close`, { body: {} }))
            }
          />,
        ])}
        {answering && (
          <Answering
            since={asked}
            nowMs={nowMs}
            doing={doingWords(going.find((j) => j.state === "running"))}
            waiting={
              going[0] && !going.some((j) => j.state === "running") ? waitText(going[0]) : ""
            }
            onStop={
              going.length
                ? () =>
                    void act(
                      () =>
                        Promise.all(going.map((j) => api(`/v1/jobs/${j.id}/cancel`, { body: {} }))),
                      t("side.stopped"),
                    )
                : undefined
            }
          />
        )}
        {/* More than one waiting: each is in its own line; here the way to each. */}
        {waitingHere.length > 1 && (
          <li className="flex flex-wrap items-center gap-x-2 text-xs">
            <b>{t("reply.others", { count: waitingHere.length })}</b>
            {waitingHere.map((box) => (
              <Button key={box.id} variant="link" size="small" onClick={() => toBox(box.id)}>
                {box.title}
              </Button>
            ))}
          </li>
        )}
        <li ref={end} aria-hidden />
      </ol>
      <AskForm name={name} right={scope} text={text} onText={setText} onSend={send} />
    </section>
  );
}

/** The answer going (definition 33.1, 45, 48.7): for how long, what the worker is doing now,
 * and stopping it where it is seen (user 2026-10-09: stopping was only in the jobs' table). */
function Answering({
  since,
  nowMs,
  doing,
  waiting,
  onStop,
}: {
  since: string | null;
  nowMs: number;
  doing: { now: string | null; done: string | null };
  /** Why the answer has not begun, when it waits (2026-10-30: "thinking" while it waited for
   * memory); empty while it goes. */
  waiting: string;
  onStop?: () => void;
}): ReactNode {
  return (
    <li className="flex flex-col gap-0.5 text-xs text-muted-foreground">
      <span className="flex items-center gap-1.5">
        <span className="size-3 animate-spin rounded-full border-2 border-processing border-t-transparent motion-reduce:animate-none" />
        {waiting || t("side.thinking")}
        {since && (
          <span className="tabular-nums">
            {t("side.thinking.seconds", { seconds: secondsSince(since, nowMs) })}
          </span>
        )}
        {onStop && (
          <Button variant="link" size="small" onClick={onStop}>
            {t("side.stop")}
          </Button>
        )}
      </span>
      {doing.now && <span className="pl-[18px]">{doing.now}</span>}
      {doing.done && <span className="pl-[18px]">{doing.done}</span>}
    </li>
  );
}
