// The one watch of the line of work, for every screen. Work started or ended away from this
// screen (another tab, an AI through MCP) is noticed (user 2026-10-15: a run started elsewhere
// finished, and the cards said "no result yet" until the page was reloaded). The line of work is
// read every few seconds while the page is in view; while work goes everything shown is read
// again every 2 s, and once more when it starts or ends. A read still going is not started again
// (2026-10-29: the workers' side, the jobs' button and the library each read again on a timer of
// their own, the workers' side everything every 2 s over reads still going; after the dev server
// restarted under the page they piled up until the browser refused them all, and the reception
// said "thinking" long after it had answered).
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { ApiError } from "@/api/client";
import type { JobList } from "@/api/types";
import { keyOf, queryClient, readApi } from "@/lib/useApi";

const BUSY_MS = 2000;
const IDLE_MS = 5000;
const JOBS = "/v1/jobs";

/** Whether the line of work changed from idle to busy or back. */
export function turned(before: boolean | null, now: boolean): boolean {
  return before !== null && before !== now;
}

/** Whether anything goes or waits in the line of work. */
export function busy(jobs: JobList | undefined): boolean {
  return Boolean(jobs && jobs.running + jobs.queued > 0);
}

/** How often the line of work is read: often while something goes. */
export function every(jobs: JobList | undefined): number {
  return busy(jobs) ? BUSY_MS : IDLE_MS;
}

/** Whether a failed read says the app does not answer (2026-10-30: quit from its small window,
 * the page stayed and its power sign could be pressed): no connection (fetch's TypeError), no
 * answer in time (the read's timeout), or the dev server's proxy finding no app (502 to 504). */
export function notAnswering(error: unknown): boolean {
  if (error instanceof ApiError) return error.status >= 502 && error.status <= 504;
  return (
    error instanceof TypeError || (error instanceof DOMException && error.name === "TimeoutError")
  );
}

/** The one watch; true while the app does not answer (its last read of the line of work). */
export function useWorkWatch(): boolean {
  const jobs = useQuery<JobList>({
    queryKey: keyOf(JOBS),
    queryFn: ({ signal }) => readApi<JobList>(JOBS, signal),
    refetchInterval: (query) => every(query.state.data),
  });
  const now = busy(jobs.data);
  const before = useRef<boolean | null>(null);
  // Each time the line of work is read (a read that failed changes nothing).
  useEffect(() => {
    if (jobs.dataUpdatedAt === 0) return;
    if (now || turned(before.current, now))
      void queryClient.invalidateQueries(
        { predicate: (query) => query.queryKey.join("/") !== keyOf(JOBS).join("/") },
        { cancelRefetch: false },
      );
    before.current = now;
  }, [jobs.dataUpdatedAt, now]);
  return jobs.isError && notAnswering(jobs.error);
}
