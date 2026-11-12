// A box as it was, shown from the talk once decided (step 24 design D3, D7; definition 40.2: a
// run is decided in the bar or its line, nothing is decided here): the target by name, its
// state then and after, the values it was applied with and what a person changed, the cost's
// basis, the reason, the target images; a failed one asks the worker again.
import { planAgainst, planChangeItems, planSaid, rowsOf } from "@/lib/decisions";
import type { ReactNode } from "react";
import { thumbnailUrl } from "@/api/client";
import type { Badge, Proposal, RunCard } from "@/api/types";
import { Button } from "@/components/ui/button";
import { t, when } from "@/i18n";
import { useModelName } from "@/lib/runChoice";
import { actorName } from "@/lib/actors";
import { runCardView } from "@/lib/cardView";
import { changedText } from "@/lib/work";
import { budgetWords } from "@/lib/selection";
import { failuresText } from "./GalleryCard";
import { RunCardView } from "./RunCardView";
import { textOf } from "@/lib/values";

type Values = Record<string, unknown>;
interface Shown {
  id: string;
  name: string;
  result?: string | null;
  adopted?: string | null;
  /** The failures since its last success (image_state.py), said as on its card. */
  failures?: Badge["failures"];
}

function LabeledRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[8.5rem_1fr] items-baseline gap-2 text-sm">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="min-w-0">{children}</span>
    </div>
  );
}

export function WorkDecision({
  proposal,
  onSeen,
  onRedo,
}: {
  proposal: Proposal;
  onSeen: () => void;
  /** Ask the worker to make it again (a box that failed). */
  onRedo: () => void;
}) {
  const modelName = useModelName();
  const preview = (proposal.preview ?? {}) as Values;
  // A box decided with changes shows the values it was applied with.
  const args: Values = {
    ...proposal.args,
    ...Object.fromEntries(Object.entries(proposal.changed ?? {}).map(([k, v]) => [k, v[1]])),
  };
  const images = (Array.isArray(preview.images) ? preview.images : []) as Shown[];
  const card = (preview.card ?? null) as RunCard | null;
  const imageName = (id: string) => images.find((i) => i.id === id)?.name ?? id;
  const said = card
    ? runCardView(
        card,
        images.map((i) => i.id),
        modelName,
      )
    : null;
  const plan = (preview.plan ?? null) as Values | null;
  const recipe = (plan?.recipe ?? null) as Values | null;
  // What it runs differently from the way the dataset last ran (definition 11.10).
  const against = planAgainst(proposal, modelName);
  const items = planChangeItems((plan?.changes ?? null) as Values | null, modelName);

  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      <div className="flex flex-col gap-0.5">
        <span className="text-xs text-muted-foreground">
          {t(`work.tool.${proposal.tool}`)} · {t(`work.box.state.${proposal.state}`)} ·{" "}
          {when(proposal.created_at)}
        </span>
        <h3 className="m-0 text-title">{proposal.title}</h3>
        <p className="m-0 text-sm">
          <span className="text-xs text-muted-foreground">{t("work.decision.reason")} </span>
          {proposal.reason}
        </p>
      </div>

      {proposal.tool === "run_start" && (
        <div className="flex flex-col gap-1.5">
          <LabeledRow label={t("box.key.model")}>
            {modelName(textOf(args.model ?? preview.model))}
          </LabeledRow>
          <LabeledRow label={t("box.key.effort")}>
            {textOf(args.effort ?? preview.effort) || "—"}
          </LabeledRow>
          <LabeledRow label={t("work.decision.budget")}>
            {t(
              "work.decision.budgetValue",
              budgetWords(args.budget_per_image_usd ?? preview.budget_per_image_usd, images.length),
            )}
          </LabeledRow>
          {said ? (
            // The server's card as a figure (definition 16, 18.3), the same as a worker's line
            // shows.
            <RunCardView view={said} nameOf={imageName} />
          ) : (
            <>
              <LabeledRow label={t("work.decision.instruction")}>
                {t(...planSaid(proposal))}
                {plan?.written_at ? (
                  <span className="text-muted-foreground">
                    {" · "}
                    {actorName(textOf(plan.written_by))} · {when(textOf(plan.written_at))}
                  </span>
                ) : null}
                {against && <span className="block text-sm">{t(...against)}</span>}
                {items.length > 0 && (
                  <ul className="m-0 list-none p-0 text-sm">
                    {items.map(([key, values], index) => (
                      <li key={`${key}-${index}`} className="break-words">
                        {t(key, values)}
                      </li>
                    ))}
                  </ul>
                )}
              </LabeledRow>
              {recipe && Number(recipe.runs) > 0 && (
                <LabeledRow label={t("work.decision.recipe")}>
                  {t("work.decision.recipeUsed", {
                    runs: textOf(recipe.runs),
                    trials: textOf(recipe.trials),
                  })}
                </LabeledRow>
              )}
              <LabeledRow label={t("work.decision.estimate")}>
                {preview.estimate_usd
                  ? t("work.decision.estimateText", {
                      usd: textOf(preview.estimate_usd),
                      per: textOf((preview.estimate_basis as Values | null)?.per_image_usd),
                      results: textOf((preview.estimate_basis as Values | null)?.results),
                    })
                  : t("work.decision.noEstimate")}
              </LabeledRow>
            </>
          )}
        </div>
      )}

      {proposal.tool === "mark" && args.target === "run" && (
        <div className="flex flex-col gap-1.5">
          {rowsOf(proposal).map((row) => (
            <LabeledRow key={row.imageId} label={row.name}>
              {row.now
                ? t("decision.change", { now: t(...row.now), after: t(...row.after) })
                : t(...row.after)}
            </LabeledRow>
          ))}
        </div>
      )}

      {proposal.tool === "mark" && args.target !== "run" && (
        <div className="flex flex-col gap-1.5">
          <LabeledRow label={t("work.decision.image")}>
            {textOf((preview.image as Values | null)?.name)}
          </LabeledRow>
          <LabeledRow label={t("work.decision.now")}>
            {t(preview.excluded_now ? "box.value.out" : "box.value.in")}
          </LabeledRow>
          <LabeledRow label={t("work.decision.after")}>
            {t(args.excluded ? "box.value.out" : "box.value.in")}
            {preview.adopted_after !== null && preview.adopted_after !== undefined
              ? ` · ${t("work.decision.adopted", {
                  now: textOf(preview.adopted_now),
                  after: textOf(preview.adopted_after),
                  total: textOf(preview.images),
                })}`
              : ""}
          </LabeledRow>
        </div>
      )}

      {images.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-xs text-muted-foreground">
            {t("work.decision.targets", { count: images.length })}
          </span>
          <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(110px,1fr))] gap-2 p-0">
            {images.map((image) => {
              const failed = failuresText(image.failures);
              return (
                <li
                  key={image.id}
                  className="flex flex-col gap-1 rounded-md border border-line bg-surface p-1"
                >
                  <img
                    src={thumbnailUrl(image.id, 320)}
                    alt={image.name}
                    loading="lazy"
                    className="aspect-[4/3] w-full rounded-sm bg-backdrop object-contain"
                  />
                  <span className="truncate text-xs font-semibold">{image.name}</span>
                  {image.result !== undefined && (
                    <span className="text-note text-muted-foreground">
                      {image.result ? t(`work.result.${image.result}`) : t("work.result.none")}
                      {image.adopted === "result" || image.adopted === "master"
                        ? ` · ${t("work.adopted")}`
                        : ""}
                    </span>
                  )}
                  {/* Apart from the result it has (Astra 2026-10-17 P02: "failed · used for
                      training" read as one state). */}
                  {failed && (
                    <span className="text-note text-failed" title={failed.full || undefined}>
                      {failed.short}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {proposal.changed && (
        <p className="m-0 text-sm">
          {t("work.decision.changedBy", {
            changes: changedText(proposal.changed, modelName),
          })}
        </p>
      )}
      {proposal.state === "failed" && (
        <p className="m-0 rounded-md border border-failed px-2.5 py-1.5 text-sm">
          {t("work.decision.failed", { message: textOf(proposal.outcome?.message) })}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
        {proposal.state === "failed" ? (
          <>
            <Button variant="primary" onClick={onRedo}>
              {t("work.decision.redo", {
                agent: t(`agent.${proposal.agent}`),
              })}
            </Button>
            {proposal.trouble && <Button onClick={onSeen}>{t("band.dismiss")}</Button>}
          </>
        ) : (
          <span className="text-sm text-muted-foreground">
            {t(`work.box.state.${proposal.state}`)}
            {proposal.decided_at ? ` · ${when(proposal.decided_at)}` : ""}
          </span>
        )}
      </div>
    </div>
  );
}
