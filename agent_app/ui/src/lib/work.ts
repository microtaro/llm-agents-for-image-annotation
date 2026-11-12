// The words of the work's lines (step 24), apart from the screen so they can be tested: what a
// person changed when applying, the server's own lines in a worker's conversation, what the
// person changed on the right, and the jobs of the line of work.
import type { AgentEvent, Job } from "@/api/types";
import { t } from "@/i18n";
import type { ModelName } from "./runChoice";
import { budgetWords } from "./selection";
import { planChangeText } from "./decisions";
import { withdrawnWhy } from "./talk";
import { skipText } from "./skips";
import { textOf } from "@/lib/values";
import { formatBytes } from "@/lib/bytes";

const LABEL: Record<string, string> = {
  count: "box.key.count",
  image_ids: "box.key.images",
  model: "box.key.model",
  effort: "box.key.effort",
  budget_per_image_usd: "box.key.budget",
  excluded: "box.key.excluded",
};

function shown(key: string, value: unknown, name: ModelName): string {
  if (key === "model" && typeof value === "string") return name(value);
  if (Array.isArray(value)) return t("box.value.images", { count: value.length });
  if (key === "excluded") return t(value ? "box.value.out" : "box.value.in");
  if (key === "budget_per_image_usd")
    return `$${typeof value === "string" || typeof value === "number" ? String(value) : ""}`;
  return typeof value === "string" || typeof value === "number" ? String(value) : "—";
}

/** What a person changed when applying, in words ("count 5→2"). */
export function changedText(
  changed: Record<string, [unknown, unknown]> | null | undefined,
  name: ModelName,
): string {
  if (!changed) return "";
  return Object.entries(changed)
    .filter(([key]) => key in LABEL)
    .map(
      ([key, [before, after]]) =>
        `${t(LABEL[key])} ${shown(key, before, name)}→${shown(key, after, name)}`,
    )
    .join(t("box.join"));
}
/** The words of the server's own line in a worker's conversation (a box decided, a run ended,
 * a request handed over). */
/** How a run ended, as its words say it (definition 50.3): stopped at its cost limit apart
 * from stopped by a person, failed for want of memory apart from other failures (2026-11-02:
 * said only as the CLI's "exit=1"), else its state. */
export function runState(status: string, errorCode: string | null | undefined): string {
  if (status === "stopped" && errorCode === "budget_reached") return "budget_reached";
  if (status === "failed" && errorCode === "memory_short") return "memory_short";
  return status;
}

export function noteText(event: Pick<AgentEvent, "data" | "text">, name: ModelName): string {
  const data = event.data ?? {};
  const note = textOf(data.note) || event.text;
  // Which images a run or a sampling was of (Sol 2026-10-08: not told).
  const images = imagesText(
    note === "run_ended" ? data.images : (data.outcome as Record<string, unknown> | null)?.images,
  );
  const of = images ? t("work.note.images", { images }) : "";
  if (note === "run_ended") {
    const limit = budgetWords(data.budget_per_image_usd, Number(data.total));
    // The images not done when some were not (10-29: the first ten read as the failed ones).
    const which = data.not_done ? "work.note.images_not_done" : "work.note.images";
    return (
      t(`work.note.run.${runState(textOf(data.status) || "failed", textOf(data.error_code))}`, {
        succeeded: textOf(data.succeeded),
        total: textOf(data.total),
        budget: limit.budget,
        limit: limit.total,
      }) + (images ? t(which, { images }) : "")
    );
  }
  if (note === "handed")
    return t("work.note.handed", { agent: t(`agent.${textOf(data.to_agent)}`) });
  // The parts of a worker's answer the server could not use, after it answered again
  // (definition 68.2).
  // A dataset the worker's answer named with another's name, after it answered again
  // (definition 73): its words are shown as they are, the right name said.
  if (note === "answer_names")
    return t("work.note.answer_names", {
      names: (Array.isArray(data.parts) ? (data.parts as Record<string, unknown>[]) : [])
        .map((p) => t("work.names.pair", { number: textOf(p.number), name: textOf(p.name) }))
        .join(t("box.join")),
    });
  if (note === "answer_unused")
    return t("work.note.answer_unused", {
      parts: (Array.isArray(data.parts) ? (data.parts as Record<string, unknown>[]) : [])
        .map((p) => t(`work.unused.${textOf(p.part)}`, { label: textOf(p.label) }))
        .join(t("box.join")),
    });
  if (note === "box_withdrawn")
    return t("work.note.box_withdrawn", {
      title: textOf(data.title),
      why: t(...withdrawnWhy(data.outcome as Record<string, unknown> | null)),
    });
  if (note === "box_made")
    return t("work.note.boxMade", {
      agent: t(`agent.${textOf(data.by_agent)}`),
      title: textOf(data.title),
    });
  // A dataset made without some files: which and why, as the screen's taking in says it
  // (definition 76).
  const outcome = (data.outcome ?? {}) as Record<string, unknown>;
  const skipped = Array.isArray(outcome.skipped) ? (outcome.skipped as { reason: string }[]) : [];
  const without = skipped.length
    ? ` ${t("create.skipped", { count: skipped.length, why: skipText(skipped) })}`
    : "";
  if (note === "box_applied" && data.changed)
    return (
      t("work.note.box.changed", {
        title: textOf(data.title),
        changes: changedText(data.changed as Record<string, [unknown, unknown]>, name),
      }) +
      without +
      of
    );
  return t(`work.note.${note}`, { title: textOf(data.title) }) + without + of;
}

/** What the person changed on the right, in words (definition 26.4: the server's plan_changes
 * of the plan before and now), as every change of a plan is said (lib/decisions). */
export function rightText(changes: Record<string, unknown> | null, nameOf: ModelName): string {
  return planChangeText(changes, nameOf) || t("right.other");
}

export function imagesText(names: unknown): string {
  if (!Array.isArray(names) || !names.length) return "";
  const shown = names.slice(0, 3).map(textOf).join(", ");
  return names.length > 3 ? t("work.note.more", { names: shown, count: names.length - 3 }) : shown;
}

/** Why a job waits, in words; held for memory, how much is free and how much it waits for
 * (2026-10-30: a 16 GB machine's answers waited with nothing said but "thinking"). */
export function waitText(job: Job): string {
  if (job.wait_reason === "memory" && job.memory?.free_mb != null)
    return t("work.wait.memoryAmount", {
      free: formatBytes(job.memory.free_mb * 1024 * 1024),
      need: formatBytes(job.memory.need_mb * 1024 * 1024),
    });
  return job.wait_reason ? t(`work.wait.${job.wait_reason}`) : "";
}

/** A job's title in words: a run's "run:3" is its kind and image count; an answer's is the
 * person's words. */
export function jobTitle(job: Job): string {
  if (job.kind === "run") {
    const [kind, count] = job.title.split(":");
    return t(kind === "trial" ? "work.job.trial" : "work.job.run", { count: count ?? "" });
  }
  // An answer: the person's words, with which kind (a quick one may hand over to one with
  // tools, the same words twice).
  return `${t(`work.job.kind.${job.kind}`)}: ${job.title}`;
}
