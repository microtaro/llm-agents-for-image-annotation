// The gallery's decision parts (types design 16.3.1; out of Gallery.tsx): the bands at the top
// (a decided box shown from the talk, the box waiting at the step), and below the "seeing" row
// what the shown box makes, by its image and its data.
import type { AgentKey, GalleryItem, Proposal } from "@/api/types";
import { type PlanTarget, type Shown, viewReplacesCards } from "@/lib/decisions";
import { SetEye } from "@/components/LooksMenu";
import { planOfBox } from "@/lib/talk";
import { type Band, DecidedBand, DecisionBand } from "./DecisionBand";
import { DecisionSwitches, DecisionView } from "./DecisionView";

export function GalleryBands({
  datasetId,
  band,
  decided,
  talking,
  onTalk,
  items,
  onSeePlan,
}: {
  datasetId: string;
  band: Band;
  /** Open the plan a run's box runs, as it holds it (from: the box). */
  onSeePlan?: (target: PlanTarget, from?: string) => void;
  /** A decided box shown from the talk (none: none shown). */
  decided: Proposal | null;
  talking: AgentKey;
  onTalk: (agent: AgentKey) => void;
  items: GalleryItem[];
}) {
  return (
    <>
      {decided && (
        <DecidedBand
          datasetId={datasetId}
          proposal={decided}
          talking={talking}
          onTalk={onTalk}
          className="mx-5 mt-3"
        />
      )}
      <DecisionBand
        datasetId={datasetId}
        band={band}
        talking={talking}
        onTalk={onTalk}
        nameOf={(id) => items.find((i) => i.image.id === id)?.image.name}
        onSeePlan={onSeePlan}
        className="mx-5 mt-3"
      />
    </>
  );
}

export function GalleryDecisionView({
  datasetId,
  box,
  shown,
  onShown,
  items,
  colors,
  nowQuery,
}: {
  datasetId: string;
  /** The box shown in the band (none: none, or folded). */
  box: Proposal | null;
  shown: Shown;
  onShown: (next: Shown) => void;
  items: GalleryItem[];
  colors: Record<string, string>;
  /** The gallery's query for the images now, with no record chosen (route.galleryQuery). */
  nowQuery: string;
}) {
  const replaces = viewReplacesCards(Boolean(box), shown);
  return (
    <>
      {box && (
        <div className="mx-5 mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
          <DecisionSwitches shown={shown} onShown={onShown} />
          <span className="flex-1" />
          {/* A box's data in the cards' place: the eye of its images here (the cards' eye is
            not shown then). */}
          {replaces && <SetEye datasetId={datasetId} plan={planOfBox(box)} />}
        </div>
      )}
      {box && replaces && (
        <DecisionView
          datasetId={datasetId}
          proposal={box}
          items={items}
          colors={colors}
          shown={shown}
          nowQuery={nowQuery}
        />
      )}
    </>
  );
}
