// What a person chose while looking, kept for the tab and shared by the screens that show it
// (user 2026-10-06: a state shown in two places must change from either side). The images
// ticked for the next run, the filter of each stage and run, and the table's finding: the
// gallery and the loupe read and change the same values, and they outlive opening an image,
// closing it and reloading. Without storage they last while the page is open.
import { useEffect, useSyncExternalStore } from "react";
import type { AgentKey, AttributeDefinition } from "@/api/types";
import { FIRST_SHOWN, type Shown } from "./decisions";
import { placeOfWorker, workerAt } from "./home";
import type { Purpose } from "./selection";
import { IMAGE_ORDERS, type ImageOrder } from "./shown";

const memory = new Map<string, string>();
const listeners = new Set<() => void>();

function readStored(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return memory.get(key) ?? null;
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) window.sessionStorage.removeItem(key);
    else window.sessionStorage.setItem(key, value);
  } catch {
    if (value === null) memory.delete(key);
    else memory.set(key, value);
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function useStored(key: string): [string | null, (value: string | null) => void] {
  const value = useSyncExternalStore(subscribe, () => readStored(key));
  return [value, (next) => write(key, next)];
}

/** The images ticked for the next run of a dataset ("pick"), as a list. */
export function usePicks(datasetId: string, place: string): [string[], (ids: string[]) => void] {
  // Kept per place (user 2026-10-13: four chosen in Apply were Plan's chosen ones too).
  const [value, set] = useStored(`agent-app.picks.${datasetId}.${place}`);
  const picks = value ? (JSON.parse(value) as string[]) : [];
  return [picks, (ids) => set(ids.length ? JSON.stringify(ids) : null)];
}

/** How a dataset's images are ordered, kept for the tab as its filter is (user 2026-10-28). */
export function useImageOrder(datasetId: string): [ImageOrder, (next: ImageOrder) => void] {
  const [value, set] = useStored(`agent-app.order.${datasetId}`);
  const order = IMAGE_ORDERS.includes(value as ImageOrder) ? (value as ImageOrder) : "old";
  return [order, (next) => set(next === "old" ? null : next)];
}

/** Which screen of Apply's right is shown, kept for the tab (user 2026-10-13: back from the
 * loupe it went back to annotating). */
export function usePurpose(datasetId: string): [Purpose, (next: Purpose) => void] {
  const [value, set] = useStored(`agent-app.purpose.${datasetId}`);
  // Annotating with AI unless using for training was chosen (definition 37).
  return [value === "use" ? "use" : "annotate", (next) => set(next === "annotate" ? null : next)];
}

/** The library's screen, chosen at the top as a dataset's (definition 60.2): taking in (the
 * default), deleting or writing out; with the datasets chosen on it. */
export type LibraryScreen = "import" | "delete" | "export";
export function useLibraryScreen(): [LibraryScreen, (next: LibraryScreen) => void] {
  const [value, set] = useStored("agent-app.library-screen");
  return [
    value === "delete" || value === "export" ? value : "import",
    (next) => set(next === "import" ? null : next),
  ];
}

/** The folder written out into last (definition 60.4), kept in this browser. */
export function useExportFolder(): [string | null, (path: string | null) => void] {
  return useLocal("agent-app.exportFolder");
}

export function useLibraryPicks(screen: LibraryScreen): [string[], (ids: string[]) => void] {
  const [value, set] = useStored(`agent-app.library-picks.${screen}`);
  const picks = value ? (JSON.parse(value) as string[]) : [];
  return [picks, (ids) => set(ids.length ? JSON.stringify(ids) : null)];
}

/** The values a person changed in the run being decided (definition 40.2): of a worker's box
 * by its id, of the person's own run by the dataset (null); the left's line and the right's bar
 * read the same, until it is decided, declined or withdrawn. */
export type RunChanges = {
  image_ids?: string[];
  model?: string;
  effort?: string;
  budget_per_image_usd?: string;
};
const runChangesKey = (datasetId: string, boxId: string | null) =>
  `agent-app.run-changes.${datasetId}.${boxId ?? "own"}`;

export function useRunChanges(
  datasetId: string,
  boxId: string | null,
): [RunChanges, (next: RunChanges) => void] {
  const [value, set] = useStored(runChangesKey(datasetId, boxId));
  return [
    value ? (JSON.parse(value) as RunChanges) : {},
    (next) => set(Object.keys(next).length ? JSON.stringify(next) : null),
  ];
}

/** The same values, read where no hook can be (a "1" typed in the talk decides the box). */
export function runChangesOf(datasetId: string, boxId: string | null): RunChanges {
  const value = readStored(runChangesKey(datasetId, boxId));
  return value ? (JSON.parse(value) as RunChanges) : {};
}

/** Gone with the run it was of: decided, declined or withdrawn. */
export function dropRunChanges(datasetId: string, boxId: string | null) {
  write(runChangesKey(datasetId, boxId), null);
}

/** The object last chosen in the loupe, marked on its table row after closing (Astra
 * 2026-10-06: the row being reviewed was lost). */
export function useLastObject(datasetId: string): [string | null, (id: string | null) => void] {
  return useStored(`agent-app.object.${datasetId}`);
}

/** The filter chip of a stage; ② and ③ per run, so another run starts unfiltered. */
export function useFilter(
  datasetId: string,
  stage: string,
  recordId: string | null,
): [string | null, (group: string | null) => void] {
  const run = stage !== "instruction" ? `.${recordId ?? ""}` : "";
  return useStored(`agent-app.filter.${datasetId}.${stage}${run}`);
}

/** The table's finding words, mode and sort of a dataset: the loupe steps in the same order,
 * and they outlive a visit to it (Astra 2026-10-06: the sort was lost, "next" ignored it). */
export interface TableFind {
  text: string;
  mode: string;
  column: string | null;
  up: boolean;
}

export function useTableFind(
  datasetId: string,
  stage = "",
): TableFind & {
  set: (text: string, mode: string) => void;
  sort: (column: string | null, up: boolean) => void;
} {
  // Per stage (Sol 2026-10-13: Apply's search stayed on in Plan).
  const [value, setValue] = useStored(`agent-app.find.${datasetId}${stage ? `.${stage}` : ""}`);
  const now: TableFind = {
    text: "",
    mode: "all",
    column: null,
    up: true,
    ...(value ? (JSON.parse(value) as Partial<TableFind>) : {}),
  };
  const save = (next: TableFind) =>
    setValue(next.text || next.mode !== "all" || next.column ? JSON.stringify(next) : null);
  return {
    ...now,
    set: (text, mode) => save({ ...now, text, mode }),
    sort: (column, up) => save({ ...now, column, up }),
  };
}

/** Add or take out one image of the ticked ones. */
export function toggled(picks: string[], imageId: string, on: boolean): string[] {
  const rest = picks.filter((id) => id !== imageId);
  return on ? [...rest, imageId] : rest;
}

/** The library's finding words and order, kept for the tab (Astra 2026-10-06: back from a
 * dataset, the words were gone). */
export function useLibraryFind(): [
  { query: string; order: string },
  (next: { query: string; order: string }) => void,
] {
  const [value, set] = useStored("agent-app.library");
  const found = value ? (JSON.parse(value) as { query: string; order: string }) : null;
  return [found ?? { query: "", order: "new" }, (next) => set(JSON.stringify(next))];
}

/** Images the AI's last answer touched, shown on the right for a moment (step 18 design 4.1:
 * what the left points at, the right shows). */
export function useHighlight(datasetId: string): [string[], (ids: string[]) => void] {
  const [value, set] = useStored(`agent-app.highlight.${datasetId}`);
  return [
    value ? (JSON.parse(value) as string[]) : [],
    (ids) => set(ids.length ? JSON.stringify(ids) : null),
  ];
}

/** What ① shows whole on the right: "current" (the draft now) or an AI answer's id (the draft
 * it wrote); null: the cards (user 2026-10-06: "Open" changed nothing while the instruction
 * panel was in the other tab; an earlier draft is to be looked at and gone back to). */
export function useDraftView(datasetId: string): [string | null, (view: string | null) => void] {
  return useStored(`agent-app.draft-view.${datasetId}`);
}

// Kept in this browser beyond the tab (a person's own arrangement of the work screen, step 24).
function readLocal(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return memory.get(`local:${key}`) ?? null;
  }
}

function writeLocal(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    if (value === null) memory.delete(`local:${key}`);
    else memory.set(`local:${key}`, value);
  }
  for (const listener of listeners) listener();
}

function useLocal(key: string): [string | null, (value: string | null) => void] {
  const value = useSyncExternalStore(subscribe, () => readLocal(key));
  return [value, (next) => writeLocal(key, next)];
}

/** Boxes put off ("later"): folded to one line, their state on the server unchanged. */
export function useLater(datasetId: string): [string[], (ids: string[]) => void] {
  const [value, set] = useStored(`agent-app.later.${datasetId}`);
  return [
    value ? (JSON.parse(value) as string[]) : [],
    (ids) => set(ids.length ? JSON.stringify(ids) : null),
  ];
}

/** A place's key for what is kept per place: a dataset's id, or the library (definition 48.6). */
export function placeKey(datasetId: string | null): string {
  return datasetId ?? "library";
}

/** The newest line seen of each worker's talk, per place (the "new" mark). */
export function useSeenLines(
  datasetId: string,
): [Partial<Record<AgentKey, number>>, (agent: AgentKey, id: number) => void] {
  const [value, set] = useLocal(`agent-app.seen.${datasetId}`);
  const seen = value ? (JSON.parse(value) as Partial<Record<AgentKey, number>>) : {};
  return [seen, (agent, id) => set(JSON.stringify({ ...seen, [agent]: id }))];
}

/** The left panel's arrangement: its width, on the right instead, folded to the buttons. */
export interface SideLayout {
  width: number;
  right: boolean;
  folded: boolean;
}

export function useSideLayout(): [SideLayout, (next: Partial<SideLayout>) => void] {
  const [value, set] = useLocal("agent-app.side-layout");
  const now: SideLayout = {
    width: 360,
    right: false,
    folded: false,
    ...(value ? (JSON.parse(value) as Partial<SideLayout>) : {}),
  };
  return [now, (next) => set(JSON.stringify({ ...now, ...next }))];
}

/** The box the band shows on each stage of a dataset (a link from the talk chooses it, from
 * the gallery or the loupe). */
export function useBandAt(
  datasetId: string,
): [Partial<Record<string, string>>, (at: Partial<Record<string, string>>) => void] {
  const [value, set] = useStored(`agent-app.band.${datasetId}`);
  return [
    value ? (JSON.parse(value) as Partial<Record<string, string>>) : {},
    (at) => set(JSON.stringify(at)),
  ];
}

/** The workers' proposals the person asked to see on the right (definition 18.2): the right
 * shows a proposal's things only when asked, never because one came. */
export function useShownOnRight(datasetId: string): [string[], (ids: string[]) => void] {
  const [value, set] = useStored(`agent-app.shown-right.${datasetId}`);
  return [
    value ? (JSON.parse(value) as string[]) : [],
    (ids) => set(ids.length ? JSON.stringify(ids) : null),
  ];
}

/** Where a box is answered: its worker's talk at the worker's place (the library's worker's
 * box of a dataset is in the library's talk, definition 48.12). */
export function talkPlaceOfBox(box: { agent: AgentKey; dataset_id: string | null }): string {
  return placeKey(placeOfWorker(box.agent) === "library" ? null : box.dataset_id);
}

/** Go to where a proposal is answered: its worker's talk, its chat, its line (18.1). */
export function toLineOfBox(box: {
  id: string;
  agent: AgentKey;
  dataset_id: string | null;
  chat_id?: number | null;
}) {
  const place = talkPlaceOfBox(box);
  write(`agent-app.talk.${place}`, box.agent);
  if (box.chat_id) {
    const key = `agent-app.chat.${place}`;
    const chats = JSON.parse(readStored(key) ?? "{}") as Record<string, number | null>;
    write(key, JSON.stringify({ ...chats, [box.agent]: box.chat_id }));
  }
  write(`agent-app.line.${place}`, `box:${box.id}`);
}

/** A line of the talk to open at, once (a version's asking words, user 2026-10-14). */
export function useLineToShow(datasetId: string): [string | null, (id: string | null) => void] {
  return useStored(`agent-app.line.${datasetId}`);
}

/** Coming in to a dataset to talk with its worker (definition 35.2): at one chat (a version's
 * "the talk it was saved from", user 2026-10-13) and one line, else at its latest chat (a request
 * the reception handed over is in a new one). */
export function enterToTalk(datasetId: string, chat?: number, line?: number) {
  if (line !== undefined) write(`agent-app.line.${datasetId}`, String(line));
  const key = `agent-app.chat.${datasetId}`;
  let chats: Record<string, number> = {};
  try {
    chats = JSON.parse(window.sessionStorage.getItem(key) ?? "{}");
  } catch {
    // No storage: the latest chat opens.
  }
  const worker = workerAt("dataset");
  const { [worker]: _, ...others } = chats;
  write(key, JSON.stringify(chat === undefined ? others : { ...others, [worker]: chat }));
}

/** The folder chosen last in the Windows window: the next window opens there (definition 43). */
export function useLastFolder(): [string | null, (path: string | null) => void] {
  return useLocal("agent-app.lastFolder");
}

/** The dataset opened last: its workers are on the left of the library (types design 16.1). */
export function useLastDataset(): [string | null, (id: string | null) => void] {
  return useLocal("agent-app.lastDataset");
}

/** Remember a dataset as the one opened last (its gallery and its loupe). */
export function useRememberDataset(datasetId: string) {
  useEffect(() => writeLocal("agent-app.lastDataset", datasetId), [datasetId]);
}

/** A decided box shown from the talk ("See proposal" on an older line): its result on the
 * right, until closed (Sol and the user 2026-10-09: nothing happened for a decided box). */
export function useViewedBox(datasetId: string): [string | null, (id: string | null) => void] {
  return useStored(`agent-app.viewed.${datasetId}`);
}

/** The chat talked in with each worker of a dataset (none: the worker's latest). */
export function useChatOf(
  datasetId: string,
): [Partial<Record<AgentKey, number>>, (agent: AgentKey, chat: number | null) => void] {
  const [value, set] = useStored(`agent-app.chat.${datasetId}`);
  const chats = value ? (JSON.parse(value) as Partial<Record<AgentKey, number>>) : {};
  return [
    chats,
    (agent, chat) => {
      const next = { ...chats };
      if (chat === null) delete next[agent];
      else next[agent] = chat;
      set(JSON.stringify(next));
    },
  ];
}

/** How a decision is shown, its image and its data (types design 16.3.1), kept for the person
 * across datasets and visits. */
export function useDecisionShown(): [Shown, (next: Shown) => void] {
  const [value, set] = useLocal("agent-app.decisionShown.targets");
  const shown = value ? (JSON.parse(value) as Shown) : FIRST_SHOWN;
  return [shown, (next) => set(JSON.stringify(next))];
}

/** A label's new field being written in the plan. */
export interface FieldWriting {
  name: string;
  type: AttributeDefinition["type"];
  choices: string;
}

/** What a person is writing in the plan (the item open to change, a rule, a label's new field),
 * kept for the tab: the right follows the talk away from the plan, and back the writing is there
 * (definition 59.5). */
export interface PlanWriting {
  editing?: "requirement" | "leave_out";
  rule?: string;
  fields?: Record<string, FieldWriting>;
}

export function usePlanWriting(datasetId: string): [PlanWriting, (next: PlanWriting) => void] {
  const [value, set] = useStored(`agent-app.plan-writing.${datasetId}`);
  const writing = value ? (JSON.parse(value) as PlanWriting) : {};
  return [writing, (next) => set(JSON.stringify(next))];
}

/** What a person is writing to each worker of a dataset, kept for the tab (Sol 2026-10-08:
 * words written to one went to the other after choosing it). Another part may begin it ("this
 * decision" asks its worker, types design 16.3.1). */
export function useAskDrafts(
  datasetId: string,
): [Partial<Record<AgentKey, string>>, (agent: AgentKey, text: string) => void] {
  const [value] = useStored(`agent-app.ask.${datasetId}`);
  const drafts = value ? (JSON.parse(value) as Partial<Record<AgentKey, string>>) : {};
  return [drafts, (agent, text) => setAskDraft(datasetId, agent, text)];
}

export function setAskDraft(datasetId: string, agent: AgentKey, text: string) {
  const key = `agent-app.ask.${datasetId}`;
  const value = readStored(key);
  const drafts = value ? (JSON.parse(value) as Partial<Record<AgentKey, string>>) : {};
  if (text) drafts[agent] = text;
  else delete drafts[agent];
  write(key, Object.keys(drafts).length ? JSON.stringify(drafts) : null);
}
