// The facts at the plan's entry (definition 34.2), shown while the server asks how the plan is
// made: the existing plans of these images (other datasets' plans, the most annotated on these
// images first, numbered as the existing plan cards are). This dataset's images are the plan
// screen's list under it, as every list of images (PlanImages; user 2026-10-28: one way of
// listing images). Nothing is chosen here; the left asks.
import type { PastRequirement } from "@/api/types";
import type { FigureImage } from "@/components/PlanFigure";
import { t } from "@/i18n";
import { definitionsOf, summaryLine } from "@/lib/planParts";
import { useApi } from "@/lib/useApi";

export function EntryFacts({
  datasetId,
  images,
}: {
  datasetId: string;
  images: Map<string, FigureImage>;
}) {
  const past = useApi<{ requirements: PastRequirement[] }>(
    `/v1/datasets/${datasetId}/plan/past?objects=false`,
  );
  const plans = past.data?.requirements ?? [];
  const cell = "border-t border-line px-3 py-1.5 align-top";
  // Numbers and counts on one line each (a header broke into a character a line).
  const head = "whitespace-nowrap px-3 py-1 font-normal";
  return (
    <div className="flex flex-col gap-5">
      <section aria-labelledby="entry-plans" className="flex flex-col gap-2">
        <h2 id="entry-plans" className="m-0 text-large">
          {t("entry.facts.plans", { count: plans.length })}
        </h2>
        {plans.length ? (
          <table className="w-full border-collapse rounded-md border border-line bg-surface text-body">
            <thead className="text-note text-muted-foreground">
              <tr>
                <th className={`${head} text-right`}>{t("entry.col.no")}</th>
                <th className={`${head} text-left`}>{t("entry.col.what")}</th>
                <th className={`${head} text-left`}>{t("entry.col.dataset")}</th>
                <th className={`${head} text-right`}>
                  {t("entry.col.done", { total: images.size })}
                </th>
                <th className={`${head} text-right`}>{t("entry.col.fixed")}</th>
              </tr>
            </thead>
            <tbody>
              {plans.map((p, i) => (
                <tr key={p.requirement_key}>
                  <td className={`${cell} text-right tabular-nums`}>{i + 1}</td>
                  <td className={cell}>
                    {summaryLine(definitionsOf(p.labels))}
                    <div className="text-note text-muted-foreground">
                      {t("entry.purpose", { purpose: p.purpose })}
                    </div>
                  </td>
                  <td className={cell}>
                    {t("past.from", { name: p.plan.dataset_name, revision: p.plan.revision })}
                  </td>
                  <td className={`${cell} whitespace-nowrap text-right tabular-nums`}>
                    {p.images ? t("entry.done", { count: p.images }) : t("entry.notYet")}
                  </td>
                  <td className={`${cell} whitespace-nowrap text-right tabular-nums`}>
                    {p.fixed ? t("entry.fixed", { count: p.fixed }) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="m-0 text-body text-muted-foreground">{t("entry.facts.none")}</p>
        )}
      </section>
    </div>
  );
}
