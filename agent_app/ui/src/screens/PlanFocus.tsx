// What the plan's screen shows above the plan (definition 26.7, 37.4): what the right is about, as
// talk.planAbout computes it from the left (a line: its open entry question's facts, what it
// showed, its trial; a box: the trial), the same computation every right takes (Astra
// 2026-10-20: "show them large" was answered, and the right did not change); with nothing, the
// trial of the plan as it is.
import type { ReactNode } from "react";
import type { AgentEvent, EntryStep, Proposal, QuestionOption, Run, Shown } from "@/api/types";
import type { FigureImage } from "@/components/PlanFigure";
import { type About, planOfBox, planShows } from "@/lib/talk";
import { EntryFacts } from "./EntryFacts";
import { LabelCompare } from "./LabelCompare";
import { RequirementCards } from "./RequirementCards";
import { TrialView } from "./TrialView";

export function planFocus({
  datasetId,
  lines,
  about,
  images,
  trialBox,
  trialRun,
}: {
  datasetId: string;
  lines: AgentEvent[];
  /** What the right shows above the plan (talk.planAbout). */
  about: About | null;
  images: Map<string, FigureImage>;
  trialBox: Proposal | undefined;
  trialRun: Run | undefined;
}): ReactNode {
  const byName = new Map([...images.values()].map((i) => [i.name, i.id]));
  const imageOf = (value: unknown) =>
    typeof value === "string" ? (images.has(value) ? value : (byName.get(value) ?? null)) : null;
  // Before it runs, its images by the plan it runs (36.1); then its record's results.
  const trial = trialBox ? (
    <TrialView
      datasetId={datasetId}
      runId={null}
      imageIds={(trialBox.args.image_ids as string[] | undefined) ?? []}
      plan={planOfBox(trialBox)}
    />
  ) : trialRun ? (
    <TrialView datasetId={datasetId} runId={trialRun.id} imageIds={[]} />
  ) : null;

  // The server's question of the plan's entry, while open (34.2): the facts, the existing
  // plans numbered as its options, or the one being chosen how to use.
  const entry = (line: AgentEvent): ReactNode => {
    const step = (line.data?.entry as { step?: EntryStep; key?: string } | undefined) ?? {};
    if (step.step === "how") return <EntryFacts datasetId={datasetId} images={images} />;
    if (step.step === "which") return <RequirementCards datasetId={datasetId} images={images} />;
    if (step.step === "keep")
      return <RequirementCards datasetId={datasetId} images={images} only={step.key ?? null} />;
    return null;
  };
  const shown = (show: Shown, line: AgentEvent): ReactNode => {
    if (show.type === "requirement")
      return (
        <RequirementCards
          datasetId={datasetId}
          images={images}
          image={imageOf(show.where.image)}
          // An open question's options take the cards' numbers (34.3).
          order={
            line.kind === "question" && !line.closed_at
              ? ((line.data?.options as QuestionOption[] | undefined) ?? []).flatMap((o) =>
                  o.key ? [o.key] : [],
                )
              : []
          }
        />
      );
    // One label: is it the same thing (definition 46, 49.2); a set of labels is not drawn here.
    if (show.type === "label" && show.id)
      return <LabelCompare datasetId={datasetId} labelId={show.id} />;
    // A record's results (a run, or the results of one record), as the trial's are.
    const record = show.type === "run" ? show.id : (show.where.run as string | undefined);
    if ((show.type === "run" || show.type === "result") && record)
      return <TrialView datasetId={datasetId} runId={record} imageIds={[]} title={show.title} />;
    return null;
  };

  // What the right was sent to (talk.planAbout), drawn as talk.planShows says (definition 37.4):
  // a line's open entry question's facts, what it showed, else the trial. A set not drawn here
  // (the plan itself) leaves the plan open below.
  const shows = planShows(about, lines);
  if (shows?.kind === "entry") return entry(shows.line);
  if (shows?.kind === "show") return shown(shows.show, shows.line);
  if (trial) return trial;
  return null;
}
