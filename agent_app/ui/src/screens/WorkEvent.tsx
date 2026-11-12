// One line of a worker's conversation (step 24), every worker's alike (definition 48.6): the
// person's words (or a request handed from another worker), the worker's answer with its boxes
// to see, a question with its options as buttons, an offer to hand the request to the worker it
// is for, a place opened (the library's worker), the server's own line (a box decided, a run
// ended, a request handed), or an answer that failed. The agent app (10-09) adds what the person
// was looking at when writing.
import type { ReactNode } from "react";
import type { AgentEvent, AgentKey, Proposal, QuestionOption, Shown } from "@/api/types";
import { Button } from "@/components/ui/button";
import { has, t, when } from "@/i18n";
import { lookingOf, optionWords, questionText, rightWords, showLinkWords } from "@/lib/talk";
import { screenName } from "@/lib/stages";
import { noteText, rightText } from "@/lib/work";
import { useModelName } from "@/lib/runChoice";
import { textOf } from "@/lib/values";

export function WorkEvent({
  event,
  onSee,
  boxOnRight,
  showOnRight = false,
  noteOnRight = null,
  onSeeNote,
  onAnswer,
  onOther,
  onHand,
  onClose,
  boxOf,
  onShow,
  reply,
  nameOf,
  onOpen,
  onGo,
}: {
  event: AgentEvent;
  /** Open a box on the right ("See proposal"); none where the right shows no box (the
   * library: its right is the datasets, where what was decided shows already). */
  onSee?: (proposalId: string) => void;
  /** Whether the right shows a box already (its link says so, not pressed; definition 37.5). */
  boxOnRight?: (proposalId: string) => boolean;
  /** Whether the right shows what this line showed already. */
  showOnRight?: boolean;
  /** A server's line's place on the right (a run ended, a request handed to the library):
   * whether it shows already; null: none (definition 59.1). */
  noteOnRight?: boolean | null;
  onSeeNote?: () => void;
  /** Answer a question with one of its options (its number in the list). */
  onAnswer: (event: AgentEvent, option: number) => void;
  /** "Other", after the options: written in the field (definition 34.3). */
  onOther?: () => void;
  onHand: (event: AgentEvent) => void;
  onClose: (event: AgentEvent) => void;
  /** A box the line points at: waiting ones and decided ones are told apart. */
  boxOf?: (proposalId: string) => Proposal | undefined;
  /** Show the set the worker named on the right (types design 3). */
  onShow?: (shown: Shown) => void;
  /** A proposal answered in the line (definition 18.1); null: only a way to it. */
  reply?: (proposalId: string, lineId: number) => ReactNode;
  /** A dataset's name, null when it was deleted (the library's lines name datasets). */
  nameOf?: (datasetId: string) => string | null;
  /** Open the place an open line names (the library's worker). */
  onOpen?: (place: Record<string, unknown>) => void;
  /** Talk with the steward of a dataset a request was handed to. */
  onGo?: (datasetId: string) => void;
}) {
  const modelName = useModelName();
  // "See proposal" says whether the box waits for the person (user 2026-10-09: a decided one
  // looked the same as one to decide).
  const seeButton = (id: string) => {
    if (!onSee) return null;
    const box = boxOf?.(id);
    const state = box?.state;
    const waiting = !box || box.waiting;
    if (boxOnRight?.(id))
      return (
        <span key={id} className="text-xs text-muted-foreground">
          {t("side.box.on", { state: t(`work.box.state.${state ?? "open"}`) })}
        </span>
      );
    return (
      <Button
        key={id}
        size="small"
        variant={waiting ? "primary" : "link"}
        onClick={() => onSee(id)}
      >
        {t("side.box.see", { state: t(`work.box.state.${state ?? "open"}`) })}
      </Button>
    );
  };
  const data = event.data ?? {};
  const time = <span className="text-note text-muted-foreground">{when(event.created_at)}</span>;
  // A dataset the line names, deleted since: said so, with no way into it (Sol 2026-10-15).
  const named = textOf(data.dataset_id);
  const gone = Boolean(named && nameOf && nameOf(named) === null);
  const goneNote = <span className="text-xs text-muted-foreground">{t("lib.gone")}</span>;
  if (event.kind === "human") {
    // Handed over by another worker (definition 36.7).
    const from = event.by.startsWith("agent:") ? (event.by.slice(6) as AgentKey) : null;
    const looked = lookingOf(event);
    return (
      <li data-line={event.id} className="flex flex-col items-end gap-0.5">
        {from && (
          <span className="text-note text-muted-foreground">
            {t("work.event.from", { agent: t(`agent.${from}`) })}
          </span>
        )}
        {looked && (
          <span className="text-note text-muted-foreground">
            {t("side.looking", { what: rightWords(looked) })}
            {looked.picked?.length
              ? ` ${t("side.looking.picked", { count: looked.picked.length })}`
              : ""}
            {looked.came_from
              ? ` ${t("side.cameLine", { agent: t(`agent.${looked.came_from}`) })}`
              : ""}
          </span>
        )}
        <p className="m-0 max-w-[85%] whitespace-pre-wrap rounded-md bg-selected px-3 py-1.5 text-body [overflow-wrap:anywhere]">
          {event.text}
        </p>
        {time}
      </li>
    );
  }
  if (event.kind === "note" && data.note === "right") {
    // What the person changed on the right, told to the plan's worker (definition 26.4).
    return (
      <li
        data-line={event.id}
        className="flex flex-wrap items-baseline gap-2 border-l-2 border-line pl-2 text-xs text-muted-foreground"
      >
        <b className="text-ink">{t("work.note.right")}</b>
        <span>{rightText(data.changes as Record<string, unknown> | null, modelName)}</span>
        {time}
      </li>
    );
  }
  if (event.kind === "note") {
    const proposal = textOf(data.proposal_id);
    // A request handed to a dataset's worker: which dataset, and the way to talk there.
    const handedTo = data.note === "handed" ? named : "";
    const name = handedTo && nameOf ? nameOf(handedTo) : null;
    return (
      <li
        data-line={event.id}
        className="flex flex-wrap items-center gap-2 border-l-2 border-line pl-2 text-xs text-muted-foreground"
      >
        <span>
          {name
            ? t("lib.handed", { name, agent: t(`agent.${textOf(data.to_agent)}`) })
            : noteText(event, modelName)}
        </span>
        {proposal && seeButton(proposal)}
        {noteOnRight === true && <span>{t("reply.onRight")}</span>}
        {noteOnRight === false && onSeeNote && (
          <Button variant="link" size="small" onClick={onSeeNote}>
            {t("reply.seeRight")}
          </Button>
        )}
        {handedTo && gone && goneNote}
        {handedTo && !gone && onGo && (
          <Button variant="link" size="small" onClick={() => onGo(handedTo)}>
            {t("lib.talkThere")}
          </Button>
        )}
        {time}
      </li>
    );
  }
  if (event.kind === "failed") {
    return (
      <li
        data-line={event.id}
        className="flex flex-col gap-1 rounded-md border border-failed bg-surface px-3 py-2 text-body"
      >
        <span className="font-semibold text-failed">{t("work.event.failed")}</span>
        {/* Its kind in the person's words when there is one (2026-10-29: "not signed in" came
            as the server's English), the server's text under it. */}
        {has(`error.${textOf(data.code)}`) && <span>{t(`error.${textOf(data.code)}`)}</span>}
        <span className="whitespace-pre-wrap text-xs text-muted-foreground">{event.text}</span>
        {!event.closed_at && (
          <span>
            <Button size="small" onClick={() => onClose(event)}>
              {t("work.seen")}
            </Button>
          </span>
        )}
      </li>
    );
  }
  const options = Array.isArray(data.options) ? (data.options as QuestionOption[]) : [];
  const answered = (data.answered as { option?: number } | undefined)?.option;
  const proposals = Array.isArray(data.proposal_ids) ? data.proposal_ids.map(textOf) : [];
  const offer = event.kind === "handoff_offer" ? textOf(data.agent) : "";
  const shown = data.show && typeof data.show === "object" ? (data.show as Shown) : null;
  return (
    <li
      data-line={event.id}
      className={`flex max-w-[92%] flex-col gap-1.5 rounded-md border px-3 py-2 text-body ${event.kind === "question" && !event.closed_at ? "border-processing bg-draft" : "border-line bg-surface"}`}
    >
      {event.kind === "question" && !event.closed_at && (
        <span className="text-xs font-semibold">{t("work.event.question")}</span>
      )}
      <p className="m-0 whitespace-pre-wrap [overflow-wrap:anywhere]">
        {event.kind === "question" ? questionText(event) : event.text}
      </p>
      {/* The options, numbered (a number typed answers too); the one recommended first; then
        "other", written in the field (34.3). The chosen one stays marked, a question set aside
        or stale cannot be answered. */}
      {event.kind === "question" && options.length > 0 && (
        <ol className="m-0 flex list-none flex-col gap-1 p-0">
          {options.map((option, index) => (
            <li key={index}>
              <Button
                size="small"
                variant={answered === index ? "primary" : undefined}
                disabled={Boolean(event.closed_at)}
                aria-pressed={answered === index}
                className="h-auto w-full justify-start whitespace-normal py-1 text-left"
                onClick={() => onAnswer(event, index)}
              >
                {index + 1}. {optionWords(option)}
                {option.recommend && ` ${t("work.option.recommend")}`}
              </Button>
            </li>
          ))}
          {!event.closed_at && onOther && (
            <li>
              <Button
                size="small"
                className="h-auto w-full justify-start whitespace-normal py-1 text-left"
                onClick={onOther}
              >
                {options.length + 1}. {t("work.option.other")}
              </Button>
            </li>
          )}
        </ol>
      )}
      {event.kind === "question" && data.stale === true && (
        <span className="text-xs text-muted-foreground">{t("work.question.stale")}</span>
      )}
      {/* Not answered: the question closes and its worker hears it (definition 44.2). */}
      {event.kind === "question" && !event.closed_at && (
        <span>
          <Button size="small" variant="link" onClick={() => onClose(event)}>
            {t("work.question.unanswer")}
          </Button>
        </span>
      )}
      {event.kind === "question" && Boolean(data.unanswered) && (
        <span className="text-xs text-muted-foreground">{t("work.question.unanswered")}</span>
      )}
      {proposals.length > 0 &&
        (reply ? (
          <div className="flex flex-col gap-1.5">
            {proposals.map((id) => reply(id, event.id) ?? seeButton(id))}
          </div>
        ) : (
          <span className="flex flex-wrap gap-1.5">{proposals.map(seeButton)}</span>
        ))}
      {shown && onShow && showOnRight && (
        <span className="text-xs text-muted-foreground">
          {t("side.show.on", { title: shown.title || t(`object.${shown.type}`) })}
        </span>
      )}
      {shown && onShow && !showOnRight && (
        <span>
          <Button
            size="small"
            variant="link"
            className="h-auto max-w-full whitespace-normal text-left"
            onClick={() => onShow(shown)}
          >
            {showLinkWords(shown)}
          </Button>
        </span>
      )}
      {/* A place the library's worker opens: its button; a deleted dataset said so. */}
      {event.kind === "open" && gone && goneNote}
      {event.kind === "open" && !gone && onOpen && (
        <span>
          <Button
            size="small"
            variant="primary"
            className="h-auto min-h-7 whitespace-normal py-1 text-left"
            onClick={() => onOpen(data)}
          >
            {placeWords(data, nameOf?.(named) ?? "")}
          </Button>
        </span>
      )}
      {/* Handed over: the server's line below says so (with the dataset it went to). */}
      {offer && !event.closed_at && gone && goneNote}
      {offer && !event.closed_at && !gone && (
        <span>
          <Button
            size="small"
            variant="primary"
            className="h-auto min-h-7 whitespace-normal py-1 text-left"
            onClick={() => onHand(event)}
          >
            {named && nameOf
              ? t("lib.handoff", { name: nameOf(named) ?? "", agent: t(`agent.${offer}`) })
              : t("work.handoff.do", { agent: t(`agent.${offer}`) })}
          </Button>
        </span>
      )}
      {time}
    </li>
  );
}

/** What an open line opens: an image, a dataset's stage, or the dataset. */
function placeWords(place: Record<string, unknown>, name: string): string {
  if (typeof place.image_name === "string") return t("lib.openImage", { image: place.image_name });
  if (place.stage === "instruction" || place.stage === "production")
    return t("lib.openStage", { name, stage: screenName(place.stage) });
  return t("lib.open", { name });
}
