// The existing plans of these images (definition 25.2-12, 26.5, 26.7, 34.2): what other datasets
// annotated or planned these images for, a card per plan, every card on the same image so they
// compare side by side (memory "compare side by side"), their rows aligned. A card: the purpose it
// was made for, the image with its annotation, the requirement's tree and the annotation's, how
// much it covers; its ways only when asked ("details"). A card's number is the left's option of
// it when a question names them (34.3), else its place in the list.
import { useState } from "react";
import type { PastRequirement } from "@/api/types";
import { SetEye } from "@/components/LooksMenu";
import { PlanFigure, type FigureImage } from "@/components/PlanFigure";
import { RequirementTree } from "@/components/RequirementTree";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { t, when } from "@/i18n";
import { definitionsOf } from "@/lib/planParts";
import { answerRows, schemaRows, unionOf } from "@/lib/requirementTree";
import { useModelName } from "@/lib/runChoice";
import { useApi } from "@/lib/useApi";

export function RequirementCards({
  datasetId,
  images,
  image: asked,
  order = [],
  only = null,
}: {
  datasetId: string;
  images: Map<string, FigureImage>;
  /** The image the worker named; else the example the server chose. */
  image?: string | null;
  /** The plans the open question's options name, in their order: first, with their numbers. */
  order?: string[];
  /** One plan alone (the one being chosen how to use), with its number in the list. */
  only?: string | null;
}) {
  const modelName = useModelName();
  const past = useApi<{ example_image: string | null; requirements: PastRequirement[] }>(
    `/v1/datasets/${datasetId}/plan/past`,
  );
  const [chosen, setChosen] = useState<string | null>(null);
  const [detail, setDetail] = useState<number | null>(null);
  const [big, setBig] = useState<number | null>(null);
  const every = past.data?.requirements ?? [];
  const named = order.filter((key) => every.some((r) => r.requirement_key === key));
  const rows = only
    ? every.flatMap((r, i) => (r.requirement_key === only ? [{ r, n: i + 1 }] : []))
    : named.length
      ? [
          ...named.map((key, i) => ({
            r: every.find((r) => r.requirement_key === key) as PastRequirement,
            n: (i + 1) as number | null,
          })),
          ...every
            .filter((r) => !named.includes(r.requirement_key))
            .map((r) => ({ r, n: null as number | null })),
        ]
      : every.map((r, i) => ({ r, n: (i + 1) as number | null }));
  const list = rows.map((row) => row.r);
  // A card's number in words that name it (an unnumbered one follows the numbered ones).
  const no = (i: number) => rows[i].n ?? i + 1;
  if (!list.length) return null;
  const imageId = chosen ?? asked ?? past.data?.example_image ?? null;
  const image = imageId ? images.get(imageId) : undefined;
  const forms = list.map((r) => definitionsOf(r.labels));
  // Aligned by the labels two cards or more have; one card's own label follows its rows (blank
  // rows for it in every other card only spread them apart).
  const all = unionOf(forms);
  const union = {
    labels: all.labels.filter(
      (l) => forms.filter((f) => f.some((d) => d.name === l.name)).length > 1,
    ),
  };
  const answered = [...new Set(list.flatMap((r) => Object.keys(r.by_image)))]
    .map((id) => images.get(id))
    .filter((i): i is FigureImage => Boolean(i))
    .sort((a, b) => a.name.localeCompare(b.name));
  const opened = big !== null ? list[big] : null;
  return (
    <section aria-labelledby="past-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 id="past-title" className="m-0 text-large">
          {t("past.title")}
        </h2>
        <span className="text-body text-muted-foreground">{t("past.sameImage")}</span>
        <label className="ml-auto flex items-center gap-2 text-body">
          {t("past.image")}
          <select
            className="rounded-md border border-line bg-surface px-2 py-0.5"
            value={imageId ?? ""}
            onChange={(e) => setChosen(e.target.value)}
          >
            {answered.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </select>
        </label>
        {/* Other datasets' plans, drawn in their colors: the eye is of this plan now. */}
        <SetEye datasetId={datasetId} plan={null} />
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(330px,1fr))] gap-3.5">
        {list.map((r, i) => {
          const objects = imageId ? r.by_image[imageId] : undefined;
          const others = forms.filter((_, k) => k !== i);
          return (
            <article
              key={r.requirement_key}
              className="flex flex-col gap-2 rounded-md border border-line bg-surface px-3 py-2.5"
            >
              <h3 className="m-0 text-title">
                {rows[i].n !== null && (
                  <span className="mr-1.5 font-normal text-muted-foreground">
                    {t("past.no", { n: rows[i].n })}
                  </span>
                )}
                {r.purpose}
              </h3>
              <span className="text-body text-muted-foreground">
                {t("past.from", { name: r.plan.dataset_name, revision: r.plan.revision })}
              </span>
              {image && objects ? (
                <PlanFigure
                  image={image}
                  objects={objects}
                  definitions={forms[i]}
                  colors={r.colors}
                  label={t("past.open", { image: image.name, n: no(i) })}
                  onOpen={() => setBig(i)}
                />
              ) : (
                // The same place empty: this requirement has nothing on the image.
                <div
                  aria-label={t("past.none", { image: image?.name ?? "", n: no(i) })}
                  className="aspect-[3/2] rounded-sm border border-dashed border-line"
                />
              )}
              <RequirementTree
                rows={schemaRows(forms[i], { union, others })}
                root={t("tree.root.schema")}
                colors={r.colors}
                only={t("past.only", { n: no(i) })}
              />
              {image && objects && (
                <RequirementTree
                  rows={answerRows(objects, forms[i], { union, folded: true }).rows}
                  root={t("tree.root.answer", { image: image.name })}
                  colors={r.colors}
                  definitions={forms[i]}
                />
              )}
              <div className="mt-auto flex flex-wrap items-center gap-1.5 text-body">
                <span className="rounded-full border border-line px-2">
                  {t("past.images", { count: r.images })}
                </span>
                <span className="rounded-full border border-line px-2">
                  {t("past.fixed", { count: r.fixed })}
                </span>
                <span className="rounded-full border border-line px-2">
                  {t("past.datasets", { count: r.datasets })}
                </span>
                <Button
                  variant="link"
                  size="small"
                  className="ml-auto"
                  aria-expanded={detail === i}
                  onClick={() => setDetail(detail === i ? null : i)}
                >
                  {t(detail === i ? "past.ways.close" : "past.ways.open")}
                </Button>
              </div>
            </article>
          );
        })}
      </div>
      {detail !== null && list[detail] && (
        <section
          aria-label={t("past.ways.title", { n: no(detail), count: list[detail].ways.length })}
          className="rounded-md border border-line bg-surface text-body"
        >
          <b className="block border-b border-line px-3 py-2">
            {t("past.ways.title", { n: no(detail), count: list[detail].ways.length })}
          </b>
          <table className="w-full border-collapse">
            <thead className="text-note text-muted-foreground">
              <tr>
                <th className="px-3 py-1 text-left font-normal">{t("past.ways.model")}</th>
                <th className="px-3 py-1 text-right font-normal">{t("past.ways.images")}</th>
                <th className="px-3 py-1 text-right font-normal">{t("past.ways.results")}</th>
                <th className="px-3 py-1 text-right font-normal">{t("past.ways.cost")}</th>
                <th className="px-3 py-1 text-left font-normal">{t("past.ways.newest")}</th>
              </tr>
            </thead>
            <tbody>
              {list[detail].ways.map((w, k) => (
                <tr key={k} className="border-t border-line">
                  <td className="px-3 py-1">{modelName(w.model)}</td>
                  <td className="px-3 py-1 text-right tabular-nums">{w.images}</td>
                  <td className="px-3 py-1 text-right tabular-nums">{w.results}</td>
                  <td className="px-3 py-1 text-right tabular-nums">
                    {w.cost_per_result === null ? "—" : `$${w.cost_per_result.toFixed(3)}`}
                  </td>
                  <td className="px-3 py-1">{when(w.newest)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <Dialog
        open={opened !== null}
        onOpenChange={(open) => !open && setBig(null)}
        title={opened && image ? t("past.big", { image: image.name, n: no(big ?? 0) }) : ""}
        full
      >
        {opened && image && imageId && (
          <div className="grid grid-cols-[minmax(0,2fr)_minmax(280px,1fr)] items-start gap-4 p-4 max-[800px]:grid-cols-1">
            <PlanFigure
              image={image}
              objects={opened.by_image[imageId] ?? []}
              definitions={forms[big ?? 0]}
              colors={opened.colors}
              label={image.name}
            />
            <RequirementTree
              rows={answerRows(opened.by_image[imageId] ?? [], forms[big ?? 0]).rows}
              root={t("tree.root.answer", { image: image.name })}
              colors={opened.colors}
              definitions={forms[big ?? 0]}
            />
          </div>
        )}
      </Dialog>
    </section>
  );
}
