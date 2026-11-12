// What the app server returns (agent_app/agent_app). Only the fields the screens use.

export type Geometry =
  | { type: "bbox"; xywh: [number, number, number, number] }
  | { type: "polygon"; points: [number, number][] }
  | { type: "mask"; bbox_xywh: [number, number, number, number]; mask_url?: string };

export interface Annotation {
  id: string;
  label: string;
  geometry: Geometry;
  attributes: Record<string, string | number>;
  parent_id: string | null;
  /** The object's number within its label, given by the server in reading order. */
  number?: number | null;
}

export interface Source {
  folder: string | null;
  count: number;
}

export interface DatasetSummary {
  id: string;
  /** What people call it by, "#12": given when it is made, never again (definition 61). */
  number: number;
  name: string;
  purpose: string;
  created_at: string;
  image_count: number;
  latest_revision: number | null;
  requirement_key: string | null;
  /** What the latest version puts on the images (definition 57). */
  labels: PutLabel[];
  /** When it was last worked on: a plan write, a version, a run, a fix or a decision. */
  last_at: string;
  sources: Source[];
  /** A few of its images, to know it by on the library's card (user 2026-10-15). */
  thumbnails: string[];
  /** The size of its images' files. */
  bytes: number;
  /** The datasets it shares images with, and how many and how big. */
  shared: SharedImages[];
}

export interface SharedImages {
  dataset_id: string;
  name: string;
  images: number;
  bytes: number;
}

/** What deleting datasets would remove (the confirmation before it). */
export interface Deletion {
  images: number;
  runs: number;
  trials: number;
  instructions: number;
  active_run: boolean;
  /** The images no other dataset uses: their rows and files go. */
  freed_images: number;
  freed_bytes: number;
  /** Of those, the ones with no source on the disk to import again. */
  unrecoverable: number;
  /** The other datasets that keep some of the images. */
  shared: SharedImages[];
}

export interface DatasetImage {
  image_id: string;
  name: string;
  width: number;
  height: number;
  position: number;
  added_at: string;
  source_path: string | null;
  excluded: boolean;
}

export interface Dataset extends DatasetSummary {
  images: DatasetImage[];
}

/** The map's two stages (types design 17.1): write the plan, carry it out. */
export type StageName = "instruction" | "production";

/** An item of the plan (definition 26.3), in the order they are asked. */
export type PlanItemName = "requirement" | "leave_out" | "references" | "trial" | "text";

/** Who decided an item: nobody yet, a worker, or a person. */
export type PlanItemStatus = "open" | "agent" | "person";

export interface PlanState {
  plan: InstructionContent | null;
  /** What a question stands on: the draft's write, else the latest version. */
  write_id: number | null;
  revision: number | null;
  items: { item: PlanItemName; status: PlanItemStatus; summary: unknown }[];
  next: PlanItemName | null;
}

/** A requirement other datasets annotated these images for (definition 26.5). */
export interface PastRequirement {
  requirement_key: string;
  labels: {
    id: string;
    name: string;
    shape: LabelDefinition["shape"];
    parent: string | null;
    attributes: Pick<AttributeDefinition, "name" | "type" | "choices">[];
  }[];
  /** Its labels' colors, of the dataset that last annotated for it. */
  colors: Record<string, string>;
  purpose: string;
  images: number;
  fixed: number;
  datasets: number;
  ways: {
    model: string;
    effort: string | null;
    images: number;
    results: number;
    datasets: number;
    /** USD for one image annotated once. */
    cost_per_result: number | null;
    newest: string;
  }[];
  by_image: Record<string, Annotation[]>;
  /** The plan to start from: the dataset's version it was annotated with last, or a plan that
   * never ran (definition 34.2). */
  plan: { dataset_id: string; dataset_name: string; revision: number };
}

/** What waits for the person in one place (definition 44.1): the library (no dataset) or a
 * dataset, every worker's together. */
export interface TurnPlace {
  dataset_id: string | null;
  name: string | null;
  boxes: number;
  questions: number;
  trouble: number;
  count: number;
}

/** The person's turns everywhere: the places with any, the library first, and their sum. */
export interface Turns {
  count: number;
  places: TurnPlace[];
}

/** A folder chosen in the Windows window (definition 43): its images not chosen are left out. */
export interface PickedFolder {
  directory: string;
  left_out: string[];
  cancelled: boolean;
}

/** One image of many (definition 25.2-18): its tiles numbered. */
export interface Sheet {
  image: string;
  tiles: {
    n: number;
    image_id: string;
    name?: string;
    dataset_id?: string;
    by?: ResultBy;
  }[];
}

/** A page of a dataset's sheets (definition 42.2): every page together is every image once. */
export interface DatasetSheet extends Sheet {
  page: number;
  pages: number;
  count: number;
}

/** A label of the library, one for every dataset (definition 26.1). */
export interface LibraryLabel {
  id: string;
  name: string;
  aliases: string[];
  description: string;
  datasets: number;
  dataset_ids?: string[];
}

/** An option of a worker's question (definitions 26.4, 33.3). */
export interface QuestionOption {
  label: string;
  recommend: boolean;
  /** The plan once chosen (checked by the server), or null. */
  plan: (InstructionContent & { leave_out: string[] }) | null;
  /** Where the draft starts again from once chosen, or null. */
  start: { kind: "blank" | "version" | "other"; dataset_id?: string; revision?: number } | null;
  alias: { label_id: string; word: string } | null;
  /** The requirement it sets, or the existing plan it names: the right's card of it takes its
   * number (definition 34.3). */
  key?: string | null;
  /** The server's own question (34.2): the screen's words for it and their values; label is
   * the worker's. */
  say?: "use" | "new" | "draft" | "plan" | "as_is" | "change";
  values?: Record<string, unknown>;
  /** The server's question it leads to, asked at once (no worker waited for). */
  ask?: { step: EntryStep; key?: string } | null;
}

/** The steps of the plan's entry the server asks (definition 34.2). */
export type EntryStep = "how" | "which" | "keep";

/** A label put on the images and how it is taken (definition 57). */
export interface PutLabel {
  name: string;
  shape: string;
  /** The label it is in, else none. */
  parent?: string | null;
  /** Its attributes' names. */
  attributes?: string[];
}

/** The images in each state by one plan's requirement and criteria (definition 57, 85.4,
 * image_state.state_counts): annotating's (done, other, running, failed, stale, none: one each),
 * checked by a person, and training's (used, excluded). */
export interface StateCounts {
  images: number;
  done: number;
  /** Annotations made by an earlier plan's criteria and not checked: not done by this plan. */
  other: number;
  checked: number;
  running: number;
  failed: number;
  stale: number;
  none: number;
  used: number;
  excluded: number;
}

export interface Progress {
  stages: { stage: StageName; state: StageState }[];
  facts: {
    images: number;
    revision: number | null;
    runs?: number;
    /** Images of the dataset with a result of the requirement (2026-10-07). */
    with_result?: number;
    /** The images in each state by the latest version's requirement (definition 57). */
    counts?: StateCounts;
    /** The run going and the stage it is of. */
    running?: { run_id: string; total: number; done: number; stage: StageName } | null;
    /** ① from the inside: who decided each item of the plan, and the next to ask. */
    instruction?: Pick<PlanState, "items" | "next"> & {
      /** A draft is the plan now: the next run keeps it as a version (types design 20.2). */
      draft: boolean;
    };
    adopted?: number;
    /** Images that should be adopted (all but the ones left out of training). */
    needed?: number;
  };
  /** The whole dataset in one line: running, what to do next, or complete. */
  overall?: {
    kind: "running" | "next" | "missing" | "other" | "complete";
    stage?: StageName;
    count?: number;
    total?: number;
    done?: number;
  };
}

/** A stage on the map: done, the next thing to do, or not yet. */
export type StageState = "done" | "now" | "todo";

export type View = "images" | "run" | "adoption";

export interface Badge {
  kind: string;
  /** A result's badge: made (found or not) and still to be made, as the server counts them. */
  succeeded?: boolean;
  waiting?: boolean;
  result_id?: string;
  /** Its record: a run, or a person's fix (definition 21.4). */
  record_id?: string;
  record_at?: string;
  model?: string;
  elapsed_ms?: number | null;
  cost_usd?: string | null;
  /** kind "excluded" in ②: a successful result exists (the card's ✓). */
  ran?: boolean;
  /** The result came from a trial (a few images of the version, run from ①). */
  trial?: boolean;
  /** The record's number in the dataset ("Record n"). */
  record_number?: number;
  /** The version the result was made with. */
  record_revision?: number;
  /** kind "stale": the version whose labels its results were made with. */
  earlier_revision?: number;
  /** kind "result": a person's fix ("human"), the AI's or one taken in (types design 7.1). */
  by?: ResultBy;
  /** The record it came from (the line under the card names it). */
  record_kind?: RecordKind;
  /** Made by the criteria it is judged by ("this") or by others ("other"); checked by a person
   * by them (definition 85.4). Null when judged by the requirement only. */
  criteria?: "this" | "other" | null;
  checked?: boolean | null;
  /** Made by other criteria and not checked: not done by the plan it is judged by. */
  other?: boolean | null;
  /** The plan's attributes its annotation now has no value of (definition 85.17). */
  unfilled?: string[];
  /** kind "result": a person chose it; a newer result came after the choice (7.2). */
  picked?: boolean;
  newer?: boolean;
  /** Runs that gave no result since the image's last success (all of them with none): how
   * many on each version, and the newest one's reason. */
  failures?: { parts: { revision: number; count: number }[]; reason: string };
}

export interface GalleryItem {
  image: {
    id: string;
    name: string;
    width: number;
    height: number;
    origin: "real" | "generated";
    source_path: string | null;
    excluded: boolean;
  };
  badge: Badge;
  annotations: Annotation[];
}

export interface GalleryPage {
  /** ② with no record chosen: "production", what training gets. */
  view: View | "production";
  record_id: string | null;
  requirement_key: string | null;
  label_colors: Record<string, string>;
  items: GalleryItem[];
  /** A record's plan's labels none of its results has (a record's view; definition 38.5). */
  missing_labels: string[];
  /** The images in each state by the requirement judged by (definition 57). */
  counts: StateCounts;
  /** For each attribute of the plan, the images it is not filled in (definition 85.17). */
  unfilled: Record<string, number>;
}

export interface AttributeDefinition {
  name: string;
  type: "text" | "number" | "choice";
  choices: string[] | null;
  description: string;
  scope?: "image" | "group";
}

export interface LabelDefinition {
  /** Its own id, kept when its name changes (the same label; definition 23). */
  id?: string;
  name: string;
  /** image: one answer for the whole image (VQA), its questions as attributes. */
  shape: "bbox" | "polygon" | "image";
  parent: string | null;
  description: string;
  attributes: AttributeDefinition[];
  scope?: "image" | "group";
}

/** An example image of the plan: a result of it chosen, at its set's revision, and a note
 * (definition 38.1). */
export interface Reference {
  image_id: string;
  /** The result chosen (an AI's or a person's fix, definition 38.1). */
  result_id: string;
  note: string;
  set_id: string;
  revision: number;
  annotations: Annotation[];
}

/** What a write of the plan's draft gives: its references are chosen by their own entries
 * (definition 38.1). */
export interface PlanInput {
  text: string;
  label_definitions: LabelDefinition[];
  /** What not to annotate, one short rule each (definition 26.2). */
  leave_out: string[];
}

export interface InstructionContent extends PlanInput {
  references: Reference[];
}

export interface Instruction extends InstructionContent {
  revision: number;
  created_at: string;
  created_by: string;
  requirement_key: string;
  /** In the list: the runs and trials that used it (types design 20.2), and the images its
   * samples (trials) annotated (definition 39.1). */
  runs?: number;
  trials?: number;
  trial_images?: number;
}

export interface InstructionDraft extends InstructionContent {
  written_by: string;
  updated_at: string;
  /** The write that is its content: a decision to run points at it (definition 11.2). None: a
   * version shown as the plan. */
  write_id?: number | null;
}

export interface Cost {
  usd: string | null;
  known_usd: string | null;
}

/** A decision (definition 21.3): what a press fixed, who decided it and who asked for it, the
 * proposal it came from (none: a person's own press). */
export interface Decision {
  id: string;
  dataset_id: string;
  kind: "run" | "stop" | "use";
  content: Record<string, unknown>;
  decided_by: string;
  requested_by: string;
  proposal_id: string | null;
  outcome: Record<string, unknown> | null;
  decided_at: string;
  /** A person's own decision just made: its title. */
  title?: string;
}

/** A record's kind: a run of the AI, a person's fix, one taken in or a label change (definition
 * 21.4, 60.11, 79). */
export type RecordKind = "run" | "fix" | "import" | "relabel" | "carry";

/** Who made what a result holds: a label change keeps the maker of the one it was made from
 * (user 2026-10-30). */
export type ResultBy = "ai" | "human" | "import";

/** A record (definition 21.4) in one shape where its kinds mean the same. */
export interface Run {
  id: string;
  kind?: RecordKind;
  /** Its number in the dataset, 1 for the first ("Record n"). */
  number?: number;
  dataset_id: string;
  /** A trial: a few images of the version, run from ① (user 2026-10-13). */
  trial?: boolean;
  /** queued: waiting in the line of work for a slot (step 24). */
  status: "queued" | "running" | "stopping" | "succeeded" | "failed" | "stopped" | "interrupted";
  /** Waiting in the line or going (queued, running, stopping), as the server counts it. */
  going: boolean;
  /** Of a saved version (not a draft's trial of before 10-13), as the server counts it. */
  of_version: boolean;
  /** Its images may use its results for training now; earlier: a version's run of an earlier
   * requirement (definition 19.5). */
  usable: boolean;
  earlier: boolean;
  instruction_revision: number;
  requirement_key: string;
  settings: {
    model?: string;
    effort?: string;
    tier?: string | null;
    /** The shared notes' version its worker read (definition 18.15). */
    shared_revision?: number | null;
  };
  started_at: string;
  ended_at: string | null;
  elapsed_ms: number | null;
  error: string | null;
  error_code: string | null;
  total: number;
  processed: number;
  succeeded: number;
  cost: Cost | null;
  /** The cost limit per image the run was started with, as text ("0.5"); null for none. */
  budget_per_image_usd?: string | null;
  /** Who decided it and who asked for it (a run's). */
  decision?: Decision | null;
  /** A person's fix: who fixed it, the result it was fixed from, its image. */
  fixed_by?: string;
  from_result_id?: string | null;
  image_id?: string;
  version?: number;
}

export interface RunModels {
  models: {
    model: string;
    display_name: string;
    efforts: string[];
    default_effort: string | null;
    /** Faster tiers instead of the standard one (fast mode). */
    speeds: { id: string; name: string; description: string }[];
  }[];
  unavailable_reason: string | null;
}

export interface ScanResult {
  files: { path: string; name: string }[];
  count: number;
  skipped: { path: string; reason: string }[];
  /** A folder written out, told by what it holds (definition 60.3); null: images, or none. */
  written: Written | null;
}

/** What a folder written out holds: this app's form (its datasets) or COCO's JSON. */
export type Written =
  | {
      kind: "app";
      path: string;
      datasets: {
        folder: string;
        name: string;
        purpose: string;
        images: number;
        revision: number | null;
        records: number;
      }[];
    }
  | {
      kind: "coco";
      path: string;
      file: string;
      images: number;
      annotations: number;
      categories: string[];
    };

/** A decision made ready in the work room (step 22, trial C): the AI's tool and its
 * arguments, why, and whether a person applied or declined it. */
/** How a plan version or a way was used (S2, definition 15.2): runs are the AI's runs, the
 * rest are images. */
export interface Usage {
  runs: number;
  trials: number;
  images: number;
  trial_images: number;
  succeeded: number;
  failed: number;
  adopted: number;
  fixed: number;
  ways?: (Usage & { model: string; effort: string })[];
}

/** Where a plan was started from (definition 15.1); null when not recorded. */
export type Origin =
  | { kind: "blank" }
  | { kind: "version"; dataset_id: string; revision: number; name?: string | null };

/** The decision card of a run, made by the server from the facts (definition 16.1). */
export interface RunCard {
  decision: "run_trial" | "run";
  weight: "light" | "heavy";
  fixes: {
    plan: {
      kind: "write" | "version" | null;
      write_id?: number | null;
      revision: number | null;
      next_revision: number | null;
    };
    model: string | null;
    effort: string | null;
    /** The version of the shared notes for every worker AI the run adds (definition 18.15). */
    shared_revision?: number | null;
    against: { revision: number; model: string; effort: string; run_number?: number | null } | null;
    changes: Record<string, unknown> | null;
  };
  happens: {
    images: number;
    new: number;
    redo: number;
    replaces: string[];
    /** A person chose their result: a success does not replace it (definition 19.6). */
    kept: string[];
    used_after: string[];
    /** Annotations made by other criteria than the plan's and not checked, and how many of them
     * the run makes again (definition 85.6). */
    other: { images: number; in_run: number };
    estimate_usd: string | null;
    /** A rough estimate from the dataset the plan came from (nothing ran here yet). */
    // The datasets of the same plan its estimate came from (none ran it here; definition 84).
    estimate_from?: { dataset_id: string; name: string | null }[] | null;
    budget_per_image_usd: string | null;
    /** Images another decided run holds (waiting or annotating): deciding is refused until it
     * ends (definition 18.13). */
    held?: { image_id: string; name: string; run_number: number | null }[];
  };
  grounds: {
    way: Usage | null;
    version: Usage | null;
    line: {
      origin?: Origin | null;
      origin_usage?: Usage;
      based_on?: { dataset_id: string; name: string | null; revision: number }[];
      derived_total?: Usage;
    };
    trials: { image_id: string; name: string; status: string; result_id: string }[];
  };
  blanks: ("first_run" | "not_tried" | "no_estimate")[];
}

/** The decisions (the server's actions.DECISIONS, definition 22.2). */
export type DecisionTool =
  | "run_start"
  | "run_stop"
  | "mark"
  | "pick"
  | "confirm"
  | "carry"
  | "dataset_add_images"
  | "dataset_remove_images"
  | "label_rename"
  | "label_change"
  | "dataset_rename"
  | "dataset_create"
  | "dataset_from"
  | "dataset_import"
  | "dataset_delete";

export interface Proposal {
  id: string;
  /** None: a decision of the library (making, combining, deleting a dataset). */
  dataset_id: string | null;
  bot: "library" | StageName;
  /** The worker it is of (step 24, definition 48.11: every box has one). */
  agent: AgentKey;
  tool: DecisionTool;
  args: Record<string, unknown>;
  title: string;
  reason: string;
  made_by: string;
  /** failed: the API refused it. withdrawn: what it stood on moved (the plan written again, a
   * decision first, what it named gone; definition 11.10, 18.13). applying: taken by one press
   * to be decided, for the moment it runs (issue #5-1). */
  state: "open" | "applying" | "applied" | "declined" | "failed" | "withdrawn";
  /** What the state says, as the server counts it: it waits for the person; it failed and the
   * person has not seen it (trouble); it was decided (applied, or failed carried out). */
  waiting: boolean;
  trouble: boolean;
  decided: boolean;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
  outcome: Record<string, unknown> | null;
  /** What it shows: the target by name, its state now and after, the cost's basis. */
  preview?: Record<string, unknown> | null;
  /** Values a person changed when applying: key -> [proposed, applied]. */
  changed?: Record<string, [unknown, unknown]> | null;
  from_event_id?: number | null;
  /** The chat of the worker's talk it was made in (its line is there). */
  chat_id?: number | null;
  seen_at?: string | null;
  /** The map's place of the box, from what it changes (agent app 3.4); agent is its author. */
  stage?: StageName | null;
  step?: "drop" | "save" | "trial" | "run" | null;
}

/** The workers of the work screen (step 24). */
/** The workers (definition 35.1): the library's reception and a dataset's steward. */
export type AgentKey = "reception" | "steward";
/** A worker's place: the library, or a dataset (definition 48.1). */
export type WorkerPlace = "library" | "dataset";

export interface AgentInfo {
  agent: AgentKey;
  icon: string;
  /** Its place: the library (the reception) or a dataset (the steward); definition 48.1. */
  place: WorkerPlace;
  /** Computed by the server: trouble (failed or outdated, not seen), you (boxes or a
   * question wait), working (jobs going or waiting), idle. */
  state: "idle" | "working" | "you" | "trouble";
  running: number;
  queued: number;
  /** Answers going or waiting (not runs). */
  answering?: number;
  /** Its answers going or waiting bound to this place's dataset: no run is decided meanwhile
   * (definition 11.10, 48.10). */
  bound?: number;
  /** The person's things: boxes to approve and questions to answer (waiting: both). */
  boxes: number;
  questions: number;
  waiting: number;
  trouble: number;
  /** The id of its newest line that is not the person's (the "new" mark). */
  last_event?: number | null;
  /** The chat of that line (unread lines in another chat open it). */
  last_event_chat?: number | null;
}

export interface AgentEvent {
  id: number;
  agent: AgentKey;
  /** open: a place the library's worker opens on the right (definition 48.3). */
  kind: "human" | "ai" | "question" | "handoff_offer" | "open" | "note" | "failed";
  text: string;
  by: string;
  created_at: string;
  model: string | null;
  elapsed_ms: number | null;
  cost: Cost | null;
  /** Its tool calls: when each started (ms after the answer began) and took (ms), 47. */
  tools: { tool: string; ok: boolean; at?: number | null; ms?: number | null }[];
  job_id: string | null;
  data: Record<string, unknown> | null;
  closed_at: string | null;
  /** The chat of the worker it is in (user 2026-10-09: chats as in any chat app). */
  chat_id?: number | null;
}

/** One of a worker's chats, in its history (the latest first). */
export interface AgentChat {
  id: number;
  created_at: string;
  updated_at: string;
  lines: number;
  /** The person's first words in it (null: nothing written yet). */
  title: string | null;
}

/** One job of the server's line of work (step 24). */
export interface Job {
  id: string;
  /** Its place: a dataset, or the library (null). */
  dataset_id: string | null;
  agent: AgentKey | null;
  kind: "run" | "answer_heavy";
  state: "queued" | "running" | "done" | "failed" | "cancelled";
  /** Waiting or going (queued, running), as the server counts it. */
  active: boolean;
  title: string;
  run_id: string | null;
  request_event_id: number | null;
  wait_reason: "slots" | "memory" | "same_agent" | "same_images" | null;
  /** Held for memory: how much is free and how much it waits for, in MB (null: not known). */
  memory?: { free_mb: number | null; need_mb: number };
  error: string | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  position: number | null;
  /** An answer ended: the kind of the line it wrote (none when it gave way to one with tools). */
  said?: AgentEvent["kind"] | null;
  /** An answer going: its worker's tool calls going now and the tools of those done (48.7). */
  doing?: { going: { tool: string; args: Record<string, unknown> }[]; done: string[] } | null;
}

export interface JobList {
  jobs: Job[];
  running: number;
  queued: number;
}

/** The types of the things on the right (types design 2). */
export type ObjectType =
  | "image"
  | "version"
  | "draft"
  | "run"
  | "result"
  | "proposal"
  | "snapshot"
  | "dataset"
  | "requirement"
  | "label"
  | "settings";

/** A worker's show, checked and counted by the server (types design 3.2). */
export interface Shown {
  type: ObjectType;
  id: string | null;
  where: Record<string, string | number | boolean | string[]>;
  count: number;
  title: string;
  /** One image or result pointed at: its image, opened large (definition 59.2). */
  image_id?: string;
  /** One result pointed at: its record and the version it ran. */
  record?: { id: string; trial: boolean; revision: number };
}

/** A set of one type (GET /objects/{type}). */
export interface ObjectSet<T = unknown> {
  type: ObjectType;
  where: Shown["where"];
  id: string | null;
  count: number;
  items: T[];
}
