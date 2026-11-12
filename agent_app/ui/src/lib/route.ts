// Where the screen is, kept in the URL hash so a link can point at a dataset, a stage of its
// map, its step and an image: #/  ·  #/d/<dataset>?stage=check&step=run&record=<record>  ·
// #/d/<dataset>/i/<image>?stage=master
// The work room's and the work screen's links (steps 22, 24: #/room/<dataset>, #/work/<dataset>)
// open the dataset (the agent app has the workers beside every screen of it).
// The stage chosen on the map decides what is looked at (viewOf); without one the gallery
// opens the stage the map marks "now".
import { useEffect, useState } from "react";
import type { ObjectType, Shown, StageName, View } from "@/api/types";
import { stageOf } from "@/lib/stages";
import type { About } from "@/lib/talk";

export type Route =
  | { screen: "library" }
  | { screen: "settings" }
  /** A set of one type a worker showed (types design 3). */
  | {
      screen: "objects";
      datasetId: string;
      type: ObjectType;
      where: Shown["where"];
      id: string | null;
      title: string;
    }
  | {
      screen: "gallery";
      datasetId: string;
      stage: StageName | null;
      recordId: string | null;
      /** The step of the stage looked at (agent app 4.3: the step decides what is shown). */
      step?: string | null;
      /** The plan its images are judged by; none: the plan now (definition 36.1). */
      plan?: PlanRef | null;
      /** The plan's screen: what it shows above the plan (definition 37.4). */
      about?: About | null;
    }
  | {
      screen: "loupe";
      datasetId: string;
      imageId: string;
      stage: StageName | null;
      recordId: string | null;
      /** An object to show selected (opened from the table). */
      objectId?: string | null;
      /** The plan its image is judged by; none: the plan now (definition 36.1). */
      plan?: PlanRef | null;
    };

/** The plan a dataset's screen judges its images by (definition 36.1): a draft write, a
 * version or a blank plan (one not begun, 49.1), the one the talk is about; none named: the plan
 * now (the draft, else the latest version). */
export type PlanRef = { write: number } | { revision: number } | { blank: true };

/** Where in a dataset the loupe opens: its image, stage, record and plan (definition 59.4). */
export type LoupeAt = Omit<Extract<Route, { screen: "loupe" }>, "screen" | "datasetId">;

/** The loupe of an image of a set (its card, the steward's one image): the set's plan and the
 * record its cards read, at Apply's stage as a set's cards open it (definition 36.2); a stage
 * named (the reception's open) at that stage. */
export function imageLoupe(
  imageId: string,
  plan: PlanRef | null,
  recordId: string | null = null,
  stage: StageName | null = "production",
): LoupeAt {
  return { imageId, stage, recordId, ...(plan ? { plan } : {}) };
}

/** The loupe of one result (a row of results, the steward's one result): its image at its
 * record, by the version it ran; a trial's at the plan's stage, as its record opens. */
export function resultLoupe(result: {
  image_id: string;
  record_id: string;
  trial: boolean;
  revision: number;
}): LoupeAt {
  return {
    imageId: result.image_id,
    stage: result.trial ? "instruction" : "production",
    recordId: result.record_id,
    ...(result.revision > 0 ? { plan: { revision: result.revision } } : {}),
  };
}

/** A plan as the server's query ("write=5", "revision=4", "blank=true"), empty for none. */
export function planQuery(plan: PlanRef | null | undefined): string {
  if (!plan) return "";
  if ("blank" in plan) return "blank=true";
  return "write" in plan ? `write=${plan.write}` : `revision=${plan.revision}`;
}

/** The conditions that name a plan (planOf reads them; a set's other conditions are apart). */
export const PLAN_FIELDS = ["write", "write_id", "revision", "blank"];

/** A plan named by a set's conditions or a question's premise, if any. */
export function planOf(where: {
  write?: unknown;
  write_id?: unknown;
  revision?: unknown;
  blank?: unknown;
}): PlanRef | null {
  if (where.blank === true || where.blank === "true") return { blank: true };
  const write = Number(where.write ?? where.write_id);
  if (Number.isInteger(write) && write > 0) return { write };
  const revision = Number(where.revision);
  if (Number.isInteger(revision) && revision > 0) return { revision };
  return null;
}

/** How a stage's cards read (step 21): ① the images, ② and ③ results (② by the masters,
 * ③ by what training gets; the gallery reads each its own way). */
export function viewOf(stage: StageName): View {
  return stage === "instruction" ? "images" : "run";
}

/** The gallery's query for what it shows, read by the loupe and a decision's data too so the
 * same image says the same everywhere (definition 14; Astra 2026-10-17 P01: a card had objects
 * and the loupe opened from it "objects (0)"). One record chosen: its results. The plan with a
 * version, and annotating with AI: each image's annotation now. Before a version, and the plan
 * otherwise: the images. Else what training uses. */
export function galleryQuery(
  stage: StageName,
  recordId: string | null,
  annotating: boolean,
  hasVersion: boolean,
  plan: PlanRef | null,
): string {
  const by = planQuery(plan);
  const view = recordId
    ? `view=run&record_id=${recordId}`
    : (stage === "instruction" || annotating) && hasVersion
      ? "view=run"
      : stage === "instruction" || !hasVersion
        ? "view=images"
        : "view=production";
  return by ? `${view}&${by}` : view;
}

/** "line:12" or "box:<id>" in a link. */
function aboutOf(value: string | null): About | null {
  const [kind, rest] = value
    ? [value.slice(0, value.indexOf(":")), value.slice(value.indexOf(":") + 1)]
    : [];
  if (kind === "line" && Number.isInteger(Number(rest)) && rest) return { line: Number(rest) };
  if (kind === "box" && rest) return { box: rest };
  return null;
}

export function parseRoute(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#/, "").split("?");
  const params = new URLSearchParams(query);
  // A link from before step 21 (five stages) opens the stage its work is in now.
  const stage = stageOf(params.get("stage"));
  // The record looked at: a run or a person's fix (definition 21.4).
  const recordId = params.get("record");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  if (parts[0] === "settings") return { screen: "settings" };
  if ((parts[0] === "work" || parts[0] === "room") && parts[1])
    return { screen: "gallery", datasetId: parts[1], stage: null, recordId: null };
  if (parts[0] === "d" && parts[1]) {
    if (parts[2] === "o" && parts[3]) {
      // The set's conditions are the query, as the server reads them (ids a comma list).
      const where: Shown["where"] = {};
      for (const [key, value] of params) if (!["id", "title"].includes(key)) where[key] = value;
      return {
        screen: "objects",
        datasetId: parts[1],
        type: parts[3] as ObjectType,
        where,
        id: params.get("id"),
        title: params.get("title") ?? "",
      };
    }
    const plan = planOf({
      write: params.get("write"),
      revision: params.get("revision"),
      blank: params.get("blank"),
    });
    if (parts[2] === "i" && parts[3]) {
      return {
        screen: "loupe",
        datasetId: parts[1],
        imageId: parts[3],
        stage,
        recordId,
        ...(params.get("obj") ? { objectId: params.get("obj") } : {}),
        ...(plan ? { plan } : {}),
      };
    }
    const step = stage ? params.get("step") : null;
    const about = aboutOf(params.get("about"));
    return {
      screen: "gallery",
      datasetId: parts[1],
      stage,
      recordId,
      ...(step ? { step } : {}),
      ...(plan ? { plan } : {}),
      ...(about ? { about } : {}),
    };
  }
  return { screen: "library" };
}

export function formatRoute(route: Route): string {
  if (route.screen === "library") return "#/";
  if (route.screen === "settings") return "#/settings";
  if (route.screen === "objects") {
    const query = new URLSearchParams(whereQuery(route.where));
    if (route.id) query.set("id", route.id);
    if (route.title) query.set("title", route.title);
    const text = query.toString();
    return `#/d/${encodeURIComponent(route.datasetId)}/o/${route.type}${text ? `?${text}` : ""}`;
  }
  const query = new URLSearchParams();
  if (route.stage) query.set("stage", route.stage);
  if (route.recordId && route.stage) query.set("record", route.recordId);
  if (route.screen === "gallery" && route.step && route.stage) query.set("step", route.step);
  if (route.screen === "gallery" && route.about)
    query.set(
      "about",
      "line" in route.about ? `line:${route.about.line}` : `box:${route.about.box}`,
    );
  if (route.screen === "loupe" && route.objectId) query.set("obj", route.objectId);
  for (const [key, value] of new URLSearchParams(planQuery(route.plan))) query.set(key, value);
  const base = `#/d/${encodeURIComponent(route.datasetId)}`;
  const tail = route.screen === "loupe" ? `/i/${encodeURIComponent(route.imageId)}` : "";
  const text = query.toString();
  return `${base}${tail}${text ? `?${text}` : ""}`;
}

// Where the loupe was opened from (Sol 2026-10-13: closed after looking at another record, or
// opened from a fixed version, it went to the gallery of that record, not back): kept when the
// screen changes into the loupe; moves inside the loupe keep it.
const LOUPE_FROM = "agent-app.loupe-from";
const isLoupe = (url: string) => /#\/d\/[^/?]+\/i\//.test(url);
// Whether the loupe was entered from another screen of this page, its one place in the history
// just after that screen's (moves inside it replace, goReplacing): closing goes back there.
let enteredLoupe = false;
if (typeof window !== "undefined")
  window.addEventListener("hashchange", (event) => {
    if (isLoupe(event.newURL) && !isLoupe(event.oldURL)) {
      enteredLoupe = true;
      try {
        sessionStorage.setItem(LOUPE_FROM, new URL(event.oldURL).hash || "#/");
      } catch {
        // No storage (a private window): the loupe goes back to its gallery.
      }
    } else if (!isLoupe(event.newURL)) enteredLoupe = false;
  });

/** The screen the loupe was opened from, if known. */
export function loupeFrom(): string | null {
  try {
    return sessionStorage.getItem(LOUPE_FROM);
  } catch {
    return null;
  }
}

export function go(route: Route) {
  window.location.hash = formatRoute(route);
}

/** A move inside a screen that keeps its one place in the history (the loupe's next image, its
 * object, its record): the browser's back and its close leave the screen, not step through it
 * (user 2026-10-23: closing the loupe opened the list again, whose back opened the loupe). */
export function goReplacing(route: Route) {
  window.location.replace(formatRoute(route));
}

/** Close the loupe: back where it was entered from, as the browser's back would; opened by a
 * link from outside, to the screen it was opened from, else to fallback. */
export function closeLoupe(datasetId: string, fallback: () => void) {
  if (enteredLoupe && window.history.length > 1) return window.history.back();
  const from = loupeFrom();
  if (from && from.startsWith(`#/d/${encodeURIComponent(datasetId)}`)) window.location.hash = from;
  else fallback();
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const changed = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  return route;
}

/** A set's conditions as the server's query (ids as a comma list). */
export function whereQuery(where: Shown["where"]): Record<string, string> {
  return Object.fromEntries(
    Object.entries(where).map(([key, value]) => [
      key,
      Array.isArray(value) ? value.join(",") : String(value),
    ]),
  );
}
