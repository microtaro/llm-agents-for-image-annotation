// The line of work as a table (step 24 design D5): instead of a kanban (user 2026-10-08: the
// workers' states and a kanban look at different things and confuse when shown together),
// opened from "going 2 · waiting 3" at the top. Every job of the dataset in order, who it is
// of, why it waits (what holds it), and the way to cancel or stop it.
import { Activity } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import type { Job, JobList } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { t, when } from "@/i18n";
import { errorText } from "@/lib/errorText";
import { queryClient, useApi } from "@/lib/useApi";
import { jobTitle, waitText } from "@/lib/work";

/** "going 2 · waiting 3" on the top row of a dataset's screens (or the library's, every
 * dataset's: null), opening the table. */
export function JobsButton({ datasetId }: { datasetId: string | null }) {
  const jobs = useApi<JobList>(datasetId ? `/v1/jobs?dataset=${datasetId}` : "/v1/jobs");
  const [open, setOpen] = useState(false);
  // Read again while anything goes or waits, until it ends, by the one watch of the line of work
  // (lib/workWatch; Sol 2026-10-09: it said "running" for minutes after the run had ended).
  const act = (path: string, done: string) =>
    void api(path, { body: {} })
      .then(() => toast.success(done))
      .catch((reason) => toast.error(errorText(reason)))
      .finally(() => void queryClient.invalidateQueries());
  return (
    <>
      {/* The work going and waiting (its list and history open from it): an icon of its own
          (user 2026-10-14: words only, it read as one of the dataset's buttons). */}
      <Button onClick={() => setOpen(true)} title={t("work.jobs.title")}>
        <Activity className="size-4" aria-hidden />
        {t("work.jobs.summary", {
          running: jobs.data?.running ?? 0,
          queued: jobs.data?.queued ?? 0,
        })}
      </Button>
      <WorkJobs
        open={open}
        onOpenChange={setOpen}
        list={jobs.data ?? null}
        onStop={(job) => act(`/v1/runs/${job.run_id}/stop`, t("work.job.stopped"))}
        onCancel={(job) => act(`/v1/jobs/${job.id}/cancel`, t("work.job.cancelled"))}
      />
    </>
  );
}

export function WorkJobs({
  open,
  onOpenChange,
  list,
  onStop,
  onCancel,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  list: JobList | null;
  onStop: (job: Job) => void;
  onCancel: (job: Job) => void;
}) {
  const jobs = list?.jobs ?? [];
  return (
    <Dialog open={open} onOpenChange={onOpenChange} title={t("work.jobs.title")} wide>
      <div className="px-5 py-3">
        {jobs.length === 0 ? (
          <p className="m-0 text-sm text-muted-foreground">{t("work.jobs.none")}</p>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-muted-foreground">
                <th className="py-1 pr-2 font-normal">{t("work.jobs.agent")}</th>
                <th className="py-1 pr-2 font-normal">{t("work.jobs.what")}</th>
                <th className="py-1 pr-2 font-normal">{t("work.jobs.state")}</th>
                <th className="py-1 pr-2 font-normal">{t("work.jobs.when")}</th>
                <th className="py-1 font-normal" />
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const live = job.active;
                return (
                  <tr key={job.id} className="border-b border-line align-top">
                    <td className="whitespace-nowrap py-1 pr-2">
                      {job.agent ? t(`agent.${job.agent}`) : ""}
                    </td>
                    <td className="py-1 pr-2">
                      <span className="line-clamp-2">{jobTitle(job)}</span>
                      {job.error && <span className="block text-xs text-failed">{job.error}</span>}
                    </td>
                    <td className="whitespace-nowrap py-1 pr-2">
                      {t(`work.job.state.${job.state}`)}
                      {/* What an answer ended in: a question waits for the person. */}
                      {job.said && (
                        <span className="block text-xs text-muted-foreground">
                          {t(`work.job.said.${job.said}`)}
                        </span>
                      )}
                      {job.state === "queued" && (
                        <span className="block text-xs text-muted-foreground">
                          {t("work.job.position", { position: job.position ?? "" })} {waitText(job)}
                        </span>
                      )}
                      {/* A run going whose next image waits for memory (2026-11-02). */}
                      {job.state === "running" && job.wait_reason && (
                        <span className="block text-xs text-muted-foreground">{waitText(job)}</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap py-1 pr-2 text-xs text-muted-foreground">
                      {when(job.ended_at ?? job.started_at ?? job.created_at)}
                    </td>
                    <td className="py-1 text-right">
                      {live &&
                        (job.kind === "run" ? (
                          <Button size="small" variant="link" onClick={() => onStop(job)}>
                            {t("work.job.stop")}
                          </Button>
                        ) : (
                          <Button size="small" variant="link" onClick={() => onCancel(job)}>
                            {t("work.job.cancel")}
                          </Button>
                        ))}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </Dialog>
  );
}
