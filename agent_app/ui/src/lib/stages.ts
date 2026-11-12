// The overall map's words for each stage, from the facts the server computed.
import type { Progress, StageName } from "@/api/types";
import { t } from "@/i18n";
import type { Purpose } from "./selection";

export const STAGES: StageName[] = ["instruction", "production"];

/** A screen on the right by the name its menu says (definition 37): the plan's, or Apply's
 * screen (annotating with AI when none is said, as a place from before the screens were). */
export function screenName(stage: StageName, screen?: Purpose | null): string {
  return stage === "instruction"
    ? t("stage.instruction")
    : t(`apply.screen.${screen ?? "annotate"}`);
}

/** The short state of one stage ("Version 1", "5 / 50", "Passed 3 / 5", …). */
export function stageText(stage: StageName, state: string, facts: Progress["facts"]): string {
  if (stage === "instruction") {
    // The plan's item to ask about next (definition 26.3).
    const next = facts.instruction?.next;
    const parts = [
      facts.revision ? t("stage.instruction.done", { revision: facts.revision }) : "",
      next ? t("stage.instruction.next", { step: t(`plan.item.${next}`) }) : "",
    ].filter(Boolean);
    return parts.length ? parts.join(" · ") : t("stage.none");
  }
  if (!facts.revision) return t("stage.none");
  if (facts.running?.stage === stage)
    return t("stage.run.running", { done: facts.running.done, total: facts.running.total });
  // ②: what training gets so far.
  if (state === "todo" && !facts.adopted) return t("stage.none");
  return t("stage.production.adopted", { count: facts.adopted ?? 0, total: facts.images });
}

/** A stage's name from before (a link, an earlier answer of the AI) as one of the two: the
 * inspection stage and its master and check, the run and the adoption → production (types
 * design 17.1). */
export function stageOf(name: string | null | undefined): StageName | null {
  if (name === "instruction" || name === "production") return name;
  if (["inspection", "master", "check", "run", "adoption"].includes(name ?? ""))
    return "production";
  return null;
}

/** The whole dataset in one line ("Complete (adopted 20)", "Next: ③ Run", …) and its color. */
export function overallText(progress: Progress | null): { text: string; tone: string } {
  const overall = progress?.overall;
  if (!overall) return { text: "…", tone: "text-muted-foreground" };
  switch (overall.kind) {
    case "complete":
      return {
        text: t("overall.complete", { count: overall.count ?? 0 }),
        tone: "text-annotated-ink",
      };
    case "running":
      return {
        text: t("overall.running", { done: overall.done ?? 0, total: overall.total ?? 0 }),
        tone: "text-action",
      };
    case "missing":
      return {
        text: t("overall.missing", { count: overall.count ?? 0 }),
        tone: "text-processing-ink",
      };
    case "other":
      return {
        text: t("overall.other", { count: overall.count ?? 0 }),
        tone: "text-processing-ink",
      };
    default: {
      // The plan being made: its item to ask about next, as ① says it (found 2026-10-06:
      // "make the instruction" above "① version 1 · next: confirm on other images").
      const step = progress?.facts.instruction?.next;
      if (overall.stage === "instruction" && step)
        return {
          text: t("overall.next.draft", { step: t(`plan.item.${step}`) }),
          tone: "text-processing-ink",
        };
      return { text: t(`overall.next.${overall.stage}`), tone: "text-processing-ink" };
    }
  }
}
