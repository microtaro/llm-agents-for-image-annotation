// The plan a box saves (design 4.5, types design 16.3.1): the draft as it will be saved (the box
// stands on it), what changes from the saved version, the output's form as a table (its labels,
// shapes and attributes; user 2026-10-12: "the output format I want to see in a table"), the
// whole text and the reference images, each the result chosen drawn (definition 38.1). Asked to
// fix it on the left, the worker writes the draft again and remakes the box; this screen then
// shows the new one. Given a version, it shows that saved plan instead (types design 4: a
// version's own screen; ① shows the current one above its images).
import type { Instruction, InstructionDraft, Reference } from "@/api/types";
import { DESCRIPTION_LINES, FoldText, TEXT_LINES } from "@/components/FoldText";
import { SetEye } from "@/components/LooksMenu";
import { t } from "@/i18n";
import { type DraftDiff, labelMark, same, sentencesOf } from "@/lib/draftText";
import { planPartItems } from "@/lib/decisions";
import { useApi } from "@/lib/useApi";
import type { Image } from "./DrawnImage";
import { PlanGets } from "./PlanGets";
import { ReferenceFigure } from "./ReferenceFigure";

export function PlanScreen({
  datasetId,
  images,
  colors,
  version,
  write,
}: {
  datasetId: string;
  images: Map<string, Image>;
  colors: Record<string, string>;
  /** A saved version ("latest" or its number) in place of the draft. */
  version?: string;
  /** A draft write as it was written (what a decision holds), in place of the draft now. */
  write?: number;
}) {
  const base = `/v1/datasets/${datasetId}/drafts/instruction`;
  const saved = useApi<Instruction>(
    version ? `/v1/datasets/${datasetId}/instructions/${version}` : null,
  );
  const written = useApi<InstructionDraft>(write ? `${base}/writes/${write}` : null);
  const fromDraft = useApi<InstructionDraft>(version || write ? null : base);
  // A version's change is from the one before it (the plan's record, types design 20.2); a
  // decision's write says its own change where it is decided.
  const diff = useApi<DraftDiff>(
    version
      ? `/v1/datasets/${datasetId}/instructions/${version}/diff`
      : write
        ? null
        : `${base}/diff`,
  );
  // A version read as a draft is.
  const plan: InstructionDraft | null = saved.data
    ? { ...saved.data, written_by: saved.data.created_by, updated_at: saved.data.created_at }
    : write
      ? written.data
      : fromDraft.data;
  const draft = { data: plan };
  if (!draft.data) return null;
  const changes = diff.data;
  const added = new Set(changes?.text.added ?? []);
  const cell = "px-2 py-1 align-top";
  return (
    <section aria-label={t("box.plan.label")} className="flex flex-col gap-3 px-5 py-3 text-body">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 className="m-0 text-heading">
          {saved.data
            ? t("plan.version.title", { revision: saved.data.revision })
            : write
              ? t("plan.write.title")
              : t("box.plan.title", { revision: (changes?.revision ?? 0) + 1 })}
        </h2>
        <span className="flex-1" />
        <SetEye
          datasetId={datasetId}
          plan={saved.data ? { revision: saved.data.revision } : write ? { write } : null}
        />
      </div>
      {changes && (
        <div className="flex flex-wrap items-center gap-2 rounded-md bg-draft px-2.5 py-1.5">
          <span className="text-muted-foreground">
            {changes.revision
              ? t("box.plan.changes", { revision: changes.revision })
              : t("box.plan.first")}
          </span>
          {same(changes) ? (
            <span>{t("draft.changes.none")}</span>
          ) : (
            planPartItems(changes).map(([key, values]) => (
              <span key={t(key, values)} className="font-semibold">
                {t(key, values)}
              </span>
            ))
          )}
          {changes.text_changed && (
            <span className="font-semibold">{t("box.plan.textChanged")}</span>
          )}
        </div>
      )}
      {/* What to read and why first, then the output's form (user 2026-10-13: "what we wanted to
        read" was nowhere to be seen; it was below the samples). */}
      <Heading who={t("plan.who.instruction")}>{t("box.plan.text")}</Heading>
      <FoldText lines={TEXT_LINES}>
        <div className="flex flex-col gap-1">
          {sentencesOf(draft.data.text).map((line, index) => (
            <p key={index} className="m-0">
              {line.map((piece, at) => (
                <span key={at} className={added.has(piece.trim()) ? "rounded-sm bg-added" : ""}>
                  {piece}
                </span>
              ))}
            </p>
          ))}
        </div>
      </FoldText>
      <Heading who={t("plan.who.output")}>
        {t("decision.output", { count: draft.data.label_definitions.length })}
      </Heading>
      <div className="max-w-full overflow-x-auto">
        <table className="w-full border-collapse text-body">
          <thead>
            <tr className="border-b border-line text-left text-muted-foreground">
              <th className={`${cell} font-normal`}>{t("decision.col.label")}</th>
              <th className={`${cell} font-normal`}>{t("decision.col.shape")}</th>
              <th className={`${cell} font-normal`}>{t("decision.col.attributes")}</th>
              <th className={`${cell} font-normal max-[640px]:hidden`}>
                {t("decision.col.description")}
              </th>
            </tr>
          </thead>
          <tbody>
            {draft.data.label_definitions.map((d) => {
              const changed = labelMark(changes, d.name);
              return [
                <tr key={d.name} className="border-b border-line max-[640px]:border-b-0">
                  <td className={`${cell} whitespace-nowrap`}>
                    <b>{d.name}</b>
                    {changed && (
                      <span className="ml-2 rounded-sm bg-added px-1 text-xs">
                        {t(`draft.mark.${changed}`)}
                      </span>
                    )}
                  </td>
                  <td className={`${cell} whitespace-nowrap`}>{t(`shape.${d.shape}`)}</td>
                  <td className={cell}>
                    {d.attributes.map((a) => a.name).join(t("box.plan.separator")) || "—"}
                  </td>
                  <td className={`${cell} text-muted-foreground max-[640px]:hidden`}>
                    {d.description ? (
                      <FoldText lines={DESCRIPTION_LINES}>{d.description}</FoldText>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>,
                // Narrow: the description on its own line under the row (Sol 2026-10-13: at
                // 256px its column was 40px wide, two letters a line).
                <tr key={`${d.name}-text`} className="border-b border-line min-[641px]:hidden">
                  <td colSpan={3} className={`${cell} pt-0 text-muted-foreground`}>
                    {d.description ? (
                      <FoldText lines={DESCRIPTION_LINES}>{d.description}</FoldText>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>,
              ];
            })}
          </tbody>
        </table>
      </div>
      <Heading who={t("plan.who.references")}>
        {t("box.plan.references", { count: draft.data.references.length })}
      </Heading>
      {draft.data.references.length === 0 && (
        <p className="m-0 text-muted-foreground">{t("box.plan.noReferences")}</p>
      )}
      <div className="flex flex-wrap gap-3">
        {draft.data.references.map((reference: Reference) => (
          <ReferenceFigure
            key={reference.image_id}
            reference={reference}
            image={images.get(reference.image_id)}
            colors={colors}
            width={328}
          />
        ))}
      </div>
      {/* What the worker AI reads besides this plan (definition 18.15). */}
      <PlanGets />
    </section>
  );
}

/** A group's heading: its name, and who reads it (definition 18.14). */
function Heading({ who, children }: { who: string; children: React.ReactNode }) {
  return (
    <h3 className="m-0 flex flex-wrap items-baseline gap-x-2 text-lead">
      <span>{children}</span>
      <span className="text-xs font-normal text-muted-foreground">{who}</span>
    </h3>
  );
}
