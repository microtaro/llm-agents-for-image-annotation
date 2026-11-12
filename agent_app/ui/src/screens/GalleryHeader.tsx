// The gallery's top row (out of Gallery.tsx, types design 17.6): where one is (the library, the
// dataset's number and name), the right's screen chosen in place of the stage's name (definition
// 35.3, 37: the plan, annotating with AI, using for training; the talk on the left goes on), and
// the operations at the right end, with the workers thinking now and for how long (34.4). Only
// these, as the library's top row (user 2026-10-28: five kinds of things in it cut the purpose
// to one character): the purpose and where the images came from are in the name's hover; the
// plan the images are judged by is in the screen's second row (PlanBasis).
import { QuitButton } from "@/components/QuitButton";
import { SettingsButton } from "@/components/SettingsButton";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import type { Dataset, JobList, Proposal, StageName } from "@/api/types";
import { answeringSince, secondsSince, useNow } from "@/lib/elapsed";
import { errorText } from "@/lib/errorText";
import { WORKERS } from "@/lib/home";
import { queryClient, useApi } from "@/lib/useApi";
import { formatRoute, go, type PlanRef } from "@/lib/route";
import type { Purpose } from "@/lib/selection";
import { screenName } from "@/lib/stages";
import { boxesOn, screenOfBox } from "@/lib/talk";
import { usePurpose } from "@/lib/viewState";
import { t } from "@/i18n";
import { JobsButton } from "./WorkJobs";
import { sourceLines } from "@/lib/sources";

export function GalleryHeader({
  datasetId,
  dataset,
  stage,
  plan,
  here,
}: {
  datasetId: string;
  dataset: Dataset | null;
  /** The place on the right (user 2026-10-16: Plan and Apply showed the same top row). */
  stage: StageName;
  /** A set shown on the right, by its title, in place of a screen (user 2026-10-23: from a
   * set no screen could be chosen); none: the screen of stage. */
  here?: string;
  /** The plan the right judges its images by, the talk's (definition 36.1); none: the plan
   * now. Kept when the screen is switched. */
  plan: PlanRef | null;
}) {
  // Its height, so the bars below stay in view under it (--gallery-head), as the loupe's.
  const head = useRef<HTMLElement>(null);
  useEffect(() => {
    const element = head.current;
    if (!element) return;
    const observer = new ResizeObserver(() =>
      document.documentElement.style.setProperty("--gallery-head", `${element.offsetHeight}px`),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const jobs = useApi<JobList>(`/v1/jobs?dataset=${datasetId}`);
  // Every worker answering bound to the dataset (its jobs, definition 48.10), as the run's
  // guard counts them (48.12).
  const thinking = WORKERS.flatMap((agent) => {
    const since = answeringSince(jobs.data?.jobs ?? [], agent);
    return since ? [{ agent, since }] : [];
  });
  const nowMs = useNow(thinking.length > 0);
  // The right's screens, each with the decisions waiting there.
  const [purpose, setPurpose] = usePurpose(datasetId);
  const proposals = useApi<{ proposals: Proposal[] }>(`/v1/datasets/${datasetId}/proposals`);
  const waitingAt = (place: StageName, screen?: Purpose) =>
    boxesOn(proposals.data?.proposals ?? [], place).filter(
      (p) => p.waiting && (!screen || screenOfBox(p) === screen),
    ).length;
  const screens: { key: "plan" | Purpose; name: string; waiting: number }[] = [
    { key: "plan", name: screenName("instruction"), waiting: waitingAt("instruction") },
    {
      key: "annotate",
      name: t("apply.screen.annotate"),
      waiting: waitingAt("production", "annotate"),
    },
    { key: "use", name: t("apply.screen.use"), waiting: waitingAt("production", "use") },
  ];
  const choose = (key: "plan" | Purpose) => {
    if (key !== "plan") setPurpose(key);
    go({
      screen: "gallery",
      datasetId,
      stage: key === "plan" ? "instruction" : "production",
      recordId: null,
      plan,
    });
  };
  const sources = sourceLines(dataset?.sources ?? []);
  return (
    // Kept at the top while the images scroll (user 2026-10-16: the way back went out of view
    // and was far), its path saying where one is and where "back" goes.
    <header
      ref={head}
      className="sticky top-0 z-30 flex flex-wrap items-center gap-x-3.5 gap-y-2 border-b border-line bg-sheet px-5 py-2.5"
    >
      {/* Where one is takes what is left; the operations stay at the right end (Astra
        2026-10-05: a long purpose pushed them to a second row, elsewhere for each dataset). */}
      <div className="flex min-w-0 flex-[1_1_420px] flex-wrap items-center gap-x-3.5 gap-y-1">
        {/* A level below the library (user 2026-10-16: "close" meant back, and the name of
            where it goes reads better than back or close). Only real levels have a path
            (user 2026-10-14: the decisions and the loupe are looked at and left). */}
        <nav
          aria-label={t("gallery.path")}
          className="flex shrink-0 items-center gap-x-1.5 text-title"
        >
          <a
            href={formatRoute({ screen: "library" })}
            title={t("gallery.close.title")}
            className="text-action underline underline-offset-2"
          >
            {t("gallery.path.library")}
          </a>
          <span aria-hidden className="text-muted-foreground">
            {t("gallery.path.separator")}
          </span>
        </nav>
        {/* The name before the purpose (user 2026-10-16: a long name broke into three lines
            beside the purpose); the purpose is cut short, whole in its hover. */}
        <h1 className="m-0 max-w-[60%] min-w-0 shrink-0 text-title [overflow-wrap:anywhere]">
          {/* The name only (user 2026-10-14: what it opened, the flow, was not known from it;
              the flow is one of Plan's other things now); pressed, it is renamed in place, as a
              document's title (user 2026-10-15: renaming is no decision of the library's). */}
          {dataset ? (
            <>
              {/* Its number, what people call it by (definition 61); the name renames. */}
              <span className="mr-1.5 text-muted-foreground tabular-nums">
                {t("dataset.number", { number: String(dataset.number) })}
              </span>
              <NameInPlace
                dataset={dataset}
                about={[
                  t("gallery.purpose", { purpose: dataset.purpose, count: dataset.image_count }),
                  ...sources,
                ]}
              />
            </>
          ) : (
            "…"
          )}
        </h1>
        {/* Where one is in it, chosen here (definition 35.3). */}
        <span className="flex shrink-0 items-center gap-x-1.5 text-title">
          <span aria-hidden className="text-muted-foreground">
            {t("gallery.path.separator")}
          </span>
          <select
            aria-label={t("apply.screen")}
            className="rounded-md border border-line bg-surface px-2 py-0.5 text-title font-semibold"
            value={here !== undefined ? "here" : stage === "instruction" ? "plan" : purpose}
            onChange={(e) => choose(e.target.value as "plan" | Purpose)}
          >
            {here !== undefined && (
              <option value="here" disabled>
                {here}
              </option>
            )}
            {screens.map((s) => (
              <option key={s.key} value={s.key}>
                {s.name}
                {s.waiting ? ` ${t("apply.screen.waiting", { count: s.waiting })}` : ""}
              </option>
            ))}
          </select>
        </span>
      </div>
      <div className="flex max-w-full shrink-0 flex-wrap items-center gap-x-3.5 gap-y-2">
        {thinking.map(({ agent, since }) => (
          <span
            key={agent}
            role="status"
            className="flex items-center gap-1.5 text-body text-muted-foreground tabular-nums"
          >
            <span className="size-3 animate-spin rounded-full border-2 border-processing border-t-transparent motion-reduce:animate-none" />
            {t("right.thinking", {
              agent: t(`agent.${agent}`),
              seconds: secondsSince(since, nowMs),
            })}
          </span>
        ))}
        <JobsButton datasetId={datasetId} />
        {/* No operations on the dataset itself: making, adding images, renaming and deleting
            are the library's decisions (user 2026-10-15); here the images are worked on. */}
        <SettingsButton />
        <ThemeToggle />
        <QuitButton />
      </div>
    </header>
  );
}

/** The name, pressed to rename in place; its hover says what the dataset is for and where its
 * images came from (user 2026-10-28: out of the top row), then that it renames. */
function NameInPlace({ dataset, about }: { dataset: Dataset; about: string[] }) {
  const [name, setName] = useState<string | null>(null);
  const save = async () => {
    const next = name?.trim();
    setName(null);
    if (!next || next === dataset.name) return;
    try {
      await api(`/v1/datasets/${dataset.id}`, { method: "PATCH", body: { name: next } });
      void queryClient.invalidateQueries();
    } catch (reason) {
      toast.error(errorText(reason));
    }
  };
  if (name === null)
    return (
      <button
        type="button"
        title={[...about, t("dataset.rename")].join("\n")}
        onClick={() => setName(dataset.name)}
        className="cursor-text rounded px-0.5 text-left hover:bg-hover"
      >
        {dataset.name}
      </button>
    );
  return (
    <input
      // oxlint-disable-next-line jsx-a11y/no-autofocus -- the name was pressed to be edited
      autoFocus
      aria-label={t("dataset.rename")}
      value={name}
      maxLength={100}
      onChange={(e) => setName(e.target.value)}
      onBlur={() => void save()}
      onKeyDown={(e) => {
        if (e.key === "Enter") void save();
        if (e.key === "Escape") setName(null);
      }}
      className="w-[24ch] max-w-full rounded-md border border-line bg-surface px-1.5 text-title"
    />
  );
}
