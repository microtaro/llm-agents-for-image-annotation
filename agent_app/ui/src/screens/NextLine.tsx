// "Do now" with the steward who does it (types design 17.5b; user 2026-10-12: "the reception's do
// now says what, but not which worker to go to"): the line, the steward's mark, and [Talk with the
// steward], which opens the dataset with its steward on the left and its stage now on the right
// (definition 35.2).
import type { Progress } from "@/api/types";
import { AgentMark } from "@/components/AgentMark";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { homeOf, workerAt } from "@/lib/home";
import { go } from "@/lib/route";
import { overallText } from "@/lib/stages";
import { enterToTalk } from "@/lib/viewState";

export function NextLine({
  datasetId,
  progress,
}: {
  datasetId: string;
  progress: Progress | null;
}) {
  const overall = overallText(progress);
  const agent = progress?.overall?.stage ? workerAt("dataset") : null;
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className={`font-semibold ${overall.tone}`}>{overall.text}</span>
      {agent && progress?.overall?.kind !== "complete" && (
        <Button
          size="small"
          variant="link"
          // Above a card's stretched link, as its other buttons are.
          className="relative z-10 gap-1 no-underline"
          title={t("next.talk", { agent: t(`agent.${agent}`) })}
          onClick={() => {
            enterToTalk(datasetId);
            go(homeOf(agent, datasetId));
          }}
        >
          <AgentMark agent={agent} />
          <span className="underline underline-offset-2">{t("agent.talk")}</span>
        </Button>
      )}
    </div>
  );
}
