// A run's decision card drawn as a figure (lib/cardView, definition 16, 18): what is used goes
// left to right in boxes (the plan, the model, the images), the record it is compared with is
// named by its number, the counts are tags, and the use of the plans is a small table with "—"
// where nothing is known (memory align-and-leave-blank). The same in a worker's line on the
// left (narrow: the boxes wrap) and in the decide window on the right.
import { ArrowDown, ArrowRight } from "lucide-react";
import { thumbnailUrl } from "@/api/client";
import type { Usage } from "@/api/types";
import { t } from "@/i18n";
import type { RunCardView as View } from "@/lib/cardView";

const SHOWN = 6;

const STATUS: Record<string, string> = {
  detected: "card.status.detected",
  not_detected: "card.status.notDetected",
  failed: "card.status.failed",
  interrupted: "card.status.interrupted",
};

function Box({ head, children }: { head: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-md border border-line bg-sheet px-2 py-1">
      <span className="text-note text-muted-foreground">{head}</span>
      <span className="font-semibold">{children}</span>
    </div>
  );
}

function Thumbs({
  ids,
  nameOf,
  marked = [],
  onSee,
}: {
  ids: string[];
  nameOf: (id: string) => string;
  marked?: string[];
  onSee?: () => void;
}) {
  return (
    <span className="flex flex-wrap items-center gap-1">
      {ids.slice(0, SHOWN).map((id) => {
        const face = (
          <>
            <img
              src={thumbnailUrl(id, 160)}
              alt=""
              className="block h-9 w-12 bg-backdrop object-cover"
            />
            {marked.includes(id) && (
              <span className="absolute inset-x-0 bottom-0 bg-processing text-center text-tiny font-semibold text-ink">
                {t("card.replaces")}
              </span>
            )}
          </>
        );
        const look = `relative overflow-hidden rounded-sm border ${marked.includes(id) ? "border-processing" : "border-line"}`;
        // Pressed only to show what the right does not show (definition 37.5).
        return onSee ? (
          <button
            key={id}
            type="button"
            title={nameOf(id)}
            aria-label={t("reply.seeImage", { name: nameOf(id) })}
            onClick={onSee}
            className={`cursor-pointer ${look}`}
          >
            {face}
          </button>
        ) : (
          <span key={id} title={nameOf(id)} className={`inline-block ${look}`}>
            {face}
          </span>
        );
      })}
      {ids.length > SHOWN && (
        <span className="text-xs text-muted-foreground">
          {t("reply.moreImages", { count: ids.length - SHOWN })}
        </span>
      )}
    </span>
  );
}

function Arrow({ narrow }: { narrow: boolean }) {
  return narrow ? (
    <ArrowDown className="ml-3 size-4 shrink-0 text-muted-foreground" aria-hidden />
  ) : (
    <ArrowRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
  );
}

const cell = (usage: Usage | null, value: (u: Usage) => string) => (usage ? value(usage) : "—");

export function RunCardView({
  view,
  nameOf,
  onSeeImages,
  narrow = false,
}: {
  view: View;
  /** In a narrow place (the talk): the boxes go down, not across. */
  narrow?: boolean;
  nameOf: (imageId: string) => string;
  /** The images on the right (the worker's line), or nothing (the decide window shows them). */
  onSeeImages?: () => void;
}) {
  return (
    <div className="flex flex-col gap-2 text-body">
      {/* Another run holds some images: said first, it is why deciding waits. */}
      {view.held && (
        <p className="m-0 rounded border border-failed bg-surface px-2 py-1">{t(...view.held)}</p>
      )}
      {/* What is used, in order: across, or down in a narrow place. */}
      <div
        className={
          narrow ? "flex flex-col items-start gap-0.5" : "flex flex-wrap items-center gap-1.5"
        }
      >
        <Box head={t("card.box.plan")}>
          {t(...view.plan)}
          {view.shared && (
            <span className="block text-xs font-normal text-muted-foreground">
              {t(...view.shared)}
            </span>
          )}
        </Box>
        <Arrow narrow={narrow} />
        <Box head={t("card.box.model")}>
          {view.model} · {view.effort}
        </Box>
        <Arrow narrow={narrow} />
        <Box head={t("card.box.images", { count: view.images.count })}>
          <Thumbs
            ids={view.images.ids}
            nameOf={nameOf}
            marked={view.replaces}
            onSee={onSeeImages}
          />
        </Box>
      </div>
      <p className="m-0 text-sm">
        {view.against ? t(...view.against.said) : t("card.against.none")}
        {view.against?.changes.map(([key, values], index) => (
          <span key={`${key}-${index}`} className="block break-words text-muted-foreground">
            {t(key, values)}
          </span>
        ))}
      </p>
      <ul className="m-0 flex list-none flex-wrap gap-1 p-0">
        {view.tags.map(([key, values]) => (
          <li
            key={key}
            className={`rounded-full border px-2 text-xs ${key === "card.tag.noCost" ? "border-dashed border-line text-muted-foreground" : "border-line bg-surface"}`}
          >
            {t(key, values)}
          </li>
        ))}
      </ul>
      {/* How the plans were used: a table, "—" where nothing is known. */}
      <table className="w-full border-collapse text-xs">
        <caption className="pb-0.5 text-left font-semibold text-muted-foreground">
          {t("card.uses.title")}
        </caption>
        <thead>
          <tr className="text-muted-foreground">
            <th className="border-b border-line py-0.5 pr-2 text-left font-normal" />
            <th className="border-b border-line px-1 py-0.5 text-right font-normal">
              {t("card.uses.runs")}
            </th>
            <th className="border-b border-line px-1 py-0.5 text-right font-normal">
              {t("card.uses.ended")}
            </th>
            <th className="border-b border-line px-1 py-0.5 text-right font-normal">
              {t("card.uses.used")}
            </th>
          </tr>
        </thead>
        <tbody>
          {view.uses.map((row) => (
            <tr key={row.label[0] + JSON.stringify(row.label[1])}>
              <th scope="row" className="border-b border-line py-0.5 pr-2 text-left font-normal">
                {t(...row.label)}
              </th>
              <td className="border-b border-line px-1 py-0.5 text-right tabular-nums">
                {cell(row.usage, (u) =>
                  t("card.uses.runsValue", { runs: u.runs, trials: u.trials }),
                )}
              </td>
              <td className="border-b border-line px-1 py-0.5 text-right tabular-nums">
                {cell(row.usage, (u) => t("card.uses.count", { count: u.images }))}
              </td>
              <td className="border-b border-line px-1 py-0.5 text-right tabular-nums">
                {cell(row.usage, (u) =>
                  u.fixed
                    ? t("card.uses.countFixed", { count: u.adopted, fixed: u.fixed })
                    : t("card.uses.count", { count: u.adopted }),
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {view.trials.length > 0 && (
        <div className="flex flex-col gap-0.5">
          <span className="text-xs font-semibold text-muted-foreground">{t("card.trials")}</span>
          <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
            {view.trials.map((trial) => (
              <li key={trial.id} className="flex items-center gap-1 text-xs">
                <img
                  src={thumbnailUrl(trial.id, 120)}
                  alt=""
                  className="h-7 w-9 rounded-sm bg-backdrop object-cover"
                />
                <span>
                  {trial.name || nameOf(trial.id)} ·{" "}
                  {t(STATUS[trial.status] ?? "card.status.going")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
