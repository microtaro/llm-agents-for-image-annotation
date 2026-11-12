// The library with its reception on the left (types design 16.1, 16.2, definition 48.6): the
// list of datasets is the reception's usual screen, and the talk with it is every worker's talk
// (Talk) at the library's place. What is the library's here is how its right follows the talk:
// a place the reception opens, and a request handed to a dataset's steward moving the left and
// the right there (definition 33.2). The steward is a dataset's (definition 35.2): choosing it
// opens the dataset opened last, at its stage now; before any was opened it cannot be chosen.
import type { ReactNode } from "react";
import type { AgentEvent, AgentKey, Dataset, StageName } from "@/api/types";
import { t } from "@/i18n";
import { homeOf, workerAt } from "@/lib/home";
import { calledName } from "@/lib/library";
import { go, imageLoupe } from "@/lib/route";
import { useApi } from "@/lib/useApi";
import { enterToTalk, useLastDataset, useSideLayout } from "@/lib/viewState";
import { AgentShell } from "./AgentShell";
import { Talk, type TalkRight } from "./Talk";
import { WorkerTabs } from "./WorkerTabs";

/** Into a dataset, to talk with its worker (definition 35.2): a request handed to it, "talk
 * there", or a place opened; the right its stage now. */
function toDatasetWorker(datasetId: string) {
  enterToTalk(datasetId);
  go(homeOf(workerAt("dataset"), datasetId));
}

/** A place the reception opens: an image in its loupe, else the dataset's screen at a stage. */
function openPlace(place: Record<string, unknown>) {
  const datasetId = String(place.dataset_id);
  enterToTalk(datasetId);
  const stage: StageName | null =
    place.stage === "instruction" || place.stage === "production" ? place.stage : null;
  go(
    typeof place.image_id === "string"
      ? { screen: "loupe", datasetId, ...imageLoupe(place.image_id, null, null, stage) }
      : { screen: "gallery", datasetId, stage, recordId: null },
  );
}

/** The library's right follows its talk: the newest line that goes somewhere (a request handed
 * to a dataset's steward, a place the person asked to open now). */
const right: TalkRight = {
  follow: (lines: AgentEvent[]) => {
    for (const line of [...lines].reverse()) {
      const handedTo = line.data?.dataset_id;
      if (line.kind === "note" && line.data?.note === "handed" && typeof handedTo === "string") {
        toDatasetWorker(handedTo);
        return;
      }
      if (line.kind === "open" && line.data?.now) {
        openPlace(line.data);
        return;
      }
    }
  },
  boxOnRight: () => false,
  shownOnRight: () => false,
  open: openPlace,
  go: toDatasetWorker,
};

export function LibraryShell({ children }: { children: ReactNode }) {
  // The library's worker is the left here; a dataset's is the one opened last's.
  const here = workerAt("library");
  const [last] = useLastDataset();
  const dataset = useApi<Dataset>(last ? `/v1/datasets/${last}` : null);
  const there = last && dataset.data ? last : null;
  const [layout, setLayout] = useSideLayout();
  const choose = (agent: AgentKey) => {
    if (agent === here) {
      if (layout.folded) setLayout({ folded: false });
      return;
    }
    if (!there) return;
    enterToTalk(there);
    go(homeOf(agent, there));
  };
  const side = (
    <aside
      aria-label={t("side.panel")}
      className="flex min-h-0 min-w-0 flex-col bg-sheet max-[999px]:max-h-[70vh] min-[1000px]:h-full"
    >
      <WorkerTabs
        current={here}
        datasetId={there}
        folded={layout.folded}
        right={layout.right}
        onChoose={choose}
        onUnfold={() => setLayout({ folded: false })}
        unavailable={(agent) => (agent !== here && !there ? t("lib.noDataset") : null)}
        note={(agent) =>
          agent === here
            ? t("lib.reception.short")
            : dataset.data
              ? t("lib.workersOf", { name: calledName(dataset.data) })
              : null
        }
      />
      {!layout.folded && (
        <Talk place={null} agent={here} scope={t("side.scope.library")} right={right} />
      )}
    </aside>
  );
  return (
    <AgentShell datasetId={there ?? ""} looking={{}} side={side}>
      {children}
    </AgentShell>
  );
}
