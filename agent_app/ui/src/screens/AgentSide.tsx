// The agent app's left inside a dataset (docs/2026-10-09-agent-app-design.md 4.2, definition
// 35.2, 48.6): the workers' buttons and the talk (Talk, every worker's alike) with the dataset's
// steward, who makes the plan and carries it out. The reception is the library's: choosing it
// goes back to the library. What is the dataset's here is how its right follows the talk: the
// state computed for what was chosen on the left (talk.rightOf and its parts, definition 35.4,
// 37.4), the one way the left moves the right.
import type { AgentEvent, AgentKey, Progress, Proposal, Run, Shown } from "@/api/types";
import { t } from "@/i18n";
import { useApi } from "@/lib/useApi";
import type { PlanTarget } from "@/lib/decisions";
import { homeOf, stageNow, workerAt } from "@/lib/home";
import { usePlanSeen } from "@/lib/planParts";
import { go, planQuery, useRoute, whereQuery } from "@/lib/route";
import { openRunBox } from "@/lib/runDecision";
import {
  type LookingAt,
  onRight,
  planAbout,
  rightOf,
  rightOfBox,
  rightOfShown,
  type RightNow,
  type RightTarget,
  rightWords,
} from "@/lib/talk";
import {
  useLater,
  usePurpose,
  useShownOnRight,
  useSideLayout,
  useViewedBox,
} from "@/lib/viewState";
import { api } from "@/api/client";
import { askToSee, useShowBox } from "./DecisionBand";
import { Talk, type TalkRight } from "./Talk";
import { WorkerTabs } from "./WorkerTabs";

/** Talk with a worker from a link elsewhere (a box's author): inside a dataset the left is
 * its worker already; another worker is talked with at its place (definition 35.2, 48.11). */
export function useTalkTo(datasetId: string) {
  return (next: AgentKey) => {
    if (next !== workerAt("dataset")) go(homeOf(next, datasetId));
  };
}

export function AgentSide({
  datasetId,
  looking,
  onSeePlan,
}: {
  datasetId: string;
  /** What the person looks at on the right, sent with the words. */
  looking: LookingAt;
  /** Open the plan a proposal runs, as it holds it (the right's plan window). */
  onSeePlan?: (target: PlanTarget, from?: string) => void;
}) {
  const base = `/v1/datasets/${datasetId}`;
  const agent = workerAt("dataset");
  const [layout, setLayout] = useSideLayout();
  const [purpose, setPurpose] = usePurpose(datasetId);
  const events = useApi<{ events: AgentEvent[] }>(`${base}/agents/${agent}/events`);
  const proposals = useApi<{ proposals: Proposal[] }>(`${base}/proposals`);
  const boxOf = (id: string) => proposals.data?.proposals.find((p) => p.id === id);
  const runBox = openRunBox(proposals.data?.proposals ?? []);
  const showBox = useShowBox(datasetId);
  const [, setViewed] = useViewedBox(datasetId);
  const runs = useApi<{ runs: Run[] }>(`${base}/runs`);
  // A run's kind and the version it ran (what the right judges its images by, 36.1).
  const runOf = (id: string) => {
    const run = runs.data?.runs.find((r) => r.id === id);
    return run ? { trial: Boolean(run.trial), revision: run.instruction_revision } : undefined;
  };
  const route = useRoute();
  // What the right shows now (definition 37.5): what the route leaves to the screen filled in as
  // the screen fills it (the stage now, the plan now, what the plan's screen shows by itself).
  const progress = useApi<Progress>(`${base}/progress`);
  const planNow = usePlanSeen(datasetId, null);
  const routePlan = usePlanSeen(datasetId, "plan" in route ? (route.plan ?? null) : null);
  const [shownRight] = useShownOnRight(datasetId);
  const [later] = useLater(datasetId);
  const [viewed] = useViewedBox(datasetId);
  const now: RightNow = {
    screen: route.screen,
    stage:
      route.screen === "gallery"
        ? (route.stage ?? (progress.data ? stageNow(progress.data) : null))
        : route.screen === "loupe"
          ? route.stage
          : null,
    purpose,
    recordId:
      route.screen === "gallery" || route.screen === "loupe" ? (route.recordId ?? null) : null,
    imageId: route.screen === "loupe" ? route.imageId : null,
    plan: planQuery(routePlan),
    about:
      route.screen === "gallery"
        ? (route.about ?? planAbout(events.data?.events ?? [], null, boxOf, runOf))
        : null,
    lines: events.data?.events ?? [],
    objects:
      route.screen === "objects"
        ? {
            type: route.type,
            where: new URLSearchParams(whereQuery(route.where)).toString(),
            id: route.id,
          }
        : null,
    // The run waiting on Apply is always the bar's there (definition 40.2).
    boxes: [...shownRight.filter((id) => !later.includes(id)), ...(runBox ? [runBox.id] : [])],
    viewed,
  };
  const isOnRight = (target: RightTarget | null) =>
    target !== null && onRight(target, now, planNow);
  // The right shows what the talk is about: where it is that already, it stays. asked: the
  // person pressed to see it (a decided box is shown with its result, its band brought into view).
  const toRight = (target: RightTarget | null, asked = false) => {
    if (!target || isOnRight(target)) return;
    if ("library" in target) {
      go({ screen: "library" });
      return;
    }
    if ("objects" in target) {
      const { type, where, id, title } = target.objects;
      go({ screen: "objects", datasetId, type, where, id, title });
      return;
    }
    if ("loupe" in target) {
      go({ screen: "loupe", datasetId, ...target.loupe });
      return;
    }
    if (target.stage === "production") {
      setPurpose(target.screen);
      // The box it is about, in the band: its targets marked on the cards (definition 37).
      const box = target.box ? boxOf(target.box) : undefined;
      if (box && asked) askToSee(box.id);
      // A waiting one in its band; a decided one asked for, with its result.
      if (box && asked) setViewed(box.waiting ? null : box.id);
      if (box && box.waiting) showBox(box);
    }
    const recordId = target.recordId ?? null;
    const about = target.stage === "instruction" ? target.about : null;
    // The plan and what the plan's screen shows go with it.
    go({
      screen: "gallery",
      datasetId,
      stage: target.stage,
      recordId,
      plan: target.plan,
      ...(about ? { about } : {}),
    });
  };
  const right: TalkRight = {
    // The newest line that points somewhere; new lines move it while the right shows a
    // dataset's screen or a set (not the loupe, where a person may be fixing).
    follow: (lines, asked) => {
      if (!asked && route.screen !== "gallery" && route.screen !== "objects") return;
      for (const line of [...lines].reverse()) {
        const target = rightOf(line, boxOf, runOf);
        if (target) {
          toRight(target, asked);
          return;
        }
      }
    },
    // A box older than the list is read for it.
    seeBox: (id) =>
      void (async () => {
        const box = boxOf(id) ?? (await api<Proposal>(`/v1/proposals/${id}`));
        toRight(rightOfBox(box), true);
      })(),
    seeShown: (shown: Shown, line: AgentEvent) =>
      toRight(rightOfShown(shown, line.id, boxOf, runOf), true),
    boxOnRight: (id) => {
      const box = boxOf(id);
      return box !== undefined && isOnRight(rightOfBox(box));
    },
    shownOnRight: (line) =>
      line.data?.show
        ? isOnRight(rightOfShown(line.data.show as Shown, line.id, boxOf, runOf))
        : false,
    // A server's line that points somewhere (a run ended, a request handed to the library) has
    // its own way there: the loupe does not follow the talk (definition 59.1).
    noteOnRight: (line) => {
      const target = line.data?.proposal_id ? null : rightOf(line, boxOf, runOf);
      return target ? isOnRight(target) : null;
    },
    seeNote: (line) => toRight(rightOf(line, boxOf, runOf), true),
    // A box decided in the talk: its place (a trial the plan, a run annotating with AI).
    decided: (box) => toRight(rightOfBox(box)),
    seePlan: onSeePlan,
  };
  // Another worker is talked with at its place: the library's at the list (definition 35.2).
  const choose = (next: AgentKey) => {
    if (layout.folded) setLayout({ folded: false });
    if (next !== agent) go(homeOf(next, datasetId));
  };

  return (
    <aside
      aria-label={t("side.panel")}
      className="flex min-h-0 min-w-0 flex-col bg-sheet max-[999px]:max-h-[70vh] min-[1000px]:h-full"
    >
      <WorkerTabs
        current={agent}
        datasetId={datasetId}
        folded={layout.folded}
        right={layout.right}
        onChoose={choose}
        onUnfold={() => setLayout({ folded: false })}
      />
      {!layout.folded && (
        <Talk
          place={datasetId}
          agent={agent}
          looking={looking}
          scope={rightWords(looking)}
          right={right}
        />
      )}
    </aside>
  );
}
