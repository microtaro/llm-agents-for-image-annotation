// How long a worker has been at an answer, in seconds that count up (definition 33.1: a spinner
// alone did not say how long it had been), on the left and on the right (34.4).
import { useEffect, useState } from "react";
import type { AgentKey, Job } from "@/api/types";
import { has, t } from "@/i18n";

/** A worker's answers going or waiting (only those asked in the given lines, when given). */
export function answeringJobs(jobs: Job[], agent: AgentKey, lines?: Set<number>): Job[] {
  return jobs.filter(
    (j) =>
      j.agent === agent &&
      j.kind !== "run" &&
      j.active &&
      (!lines || (j.request_event_id !== null && lines.has(j.request_event_id))),
  );
}

/** Since when the first of them was asked for, or null. */
export function answeringSince(jobs: Job[], agent: AgentKey, lines?: Set<number>): string | null {
  return (
    answeringJobs(jobs, agent, lines)
      .map((j) => j.created_at)
      .sort()[0] ?? null
  );
}

/** Whole seconds from an ISO time to nowMs, never below 0. */
export function secondsSince(iso: string, nowMs: number): number {
  return Math.max(0, Math.floor((nowMs - Date.parse(iso)) / 1000));
}

/** The time now, read again every second while on. */
export function useNow(on: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!on) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [on]);
  return now;
}

/** A tool by name, its words or the tool's own name; a call of a type (read:version,
 * definition 51.6) says the type, and a page of a dataset's images its page. */
export function toolName(name: string, args: Record<string, unknown> = {}): string {
  const [tool, kind] = name.split(":");
  const page = typeof args.page === "number" && args.page > 1 ? args.page : null;
  const words = has(`tool.${tool}`)
    ? t(`tool.${tool}`, { type: kind && has(`object.${kind}`) ? t(`object.${kind}`) : kind })
    : tool;
  return page ? words + t("tool.page", { page }) : words;
}

/** What a worker is doing, in words (definition 48.7): the tools going now, and those done so
 * far with how many times each (a tool takes a moment; the model's turn most of the time). */
export function doingWords(job: Job | undefined): { now: string | null; done: string | null } {
  const going = job?.doing?.going ?? [];
  const counts = new Map<string, number>();
  for (const tool of job?.doing?.done ?? []) counts.set(tool, (counts.get(tool) ?? 0) + 1);
  return {
    now: going.length
      ? t("doing.now", { what: going.map((c) => toolName(c.tool, c.args)).join(t("doing.join")) })
      : null,
    done: counts.size
      ? t("doing.done", {
          what: [...counts]
            .map(([tool, count]) => t("doing.count", { what: toolName(tool), count }))
            .join(t("doing.join")),
        })
      : null,
  };
}
