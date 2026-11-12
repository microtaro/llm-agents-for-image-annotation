// The whole instruction draft on the right of ①, with what changed marked in it (step 19 design
// 12; user 2026-10-06: the newest whole is what is wanted, the changes inside it), compared with
// the saved version. Read only: the workers write the draft (the agent app, 10-09; the progress
// panel's AI and its answers' drafts are gone with it).
import { useEffect, useState } from "react";
import { ApiError } from "@/api/client";
import type { InstructionDraft } from "@/api/types";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { type DraftDiff, labelMark, same, sentencesOf } from "@/lib/draftText";
import { planPartItems } from "@/lib/decisions";
import { useApi } from "@/lib/useApi";

export function DraftView({
  datasetId,
  onView,
}: {
  datasetId: string;
  /** "current": the draft now (the only one shown; kept for the stored value). */
  view: string;
  onView: (view: string | null) => void;
}) {
  const base = `/v1/datasets/${datasetId}/drafts/instruction`;
  const current = useApi<InstructionDraft>(base);
  const versionDiff = useApi<DraftDiff>(`${base}/diff`);
  // The whole text plain at first; the marks only when asked (user 2026-10-06: marked all
  // over, the instruction was hard to read).
  const [marking, setMarking] = useState(false);
  const content = current.data;

  // No draft any more (none, or it failed to read): the view closes.
  const gone = !current.loading && (current.error instanceof ApiError || current.data === null);
  useEffect(() => {
    if (gone) onView(null);
  }, [gone, onView]);
  if (!content) return null;
  const diff = marking ? versionDiff.data : null;
  const added = new Set(diff?.text.added ?? []);

  return (
    <section className="flex scroll-mt-(--stage-bar) flex-col gap-3 border-b border-line bg-surface px-5 py-3 text-body">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="m-0 text-heading">{t("draft.full.title")}</h2>
        <span className="flex-1" />
        <Button size="small" onClick={() => onView(null)}>
          {t("common.close")}
        </Button>
      </div>
      <label className="flex items-center gap-1.5 text-muted-foreground">
        <input type="checkbox" checked={marking} onChange={(e) => setMarking(e.target.checked)} />
        {t("draft.marks")}
      </label>
      {/* What it is compared with: the saved version. */}
      {marking && (
        <div className="flex flex-wrap items-center gap-2 rounded-md bg-draft px-2.5 py-1.5">
          <span className="text-muted-foreground">{t("draft.against")}</span>
          <span>
            {versionDiff.data?.revision
              ? t("draft.against.version", { revision: versionDiff.data.revision })
              : t("draft.against.none")}
          </span>
          {diff && same(diff) && (
            <span className="text-muted-foreground">{t("draft.changes.none")}</span>
          )}
          {diff &&
            planPartItems(diff).map(([key, values]) => (
              <span key={t(key, values)} className="font-semibold">
                {t(key, values)}
              </span>
            ))}
        </div>
      )}
      {diff && diff.text.removed.length > 0 && (
        <div>
          <span className="text-muted-foreground">{t("draft.changes.text.removed")}</span>
          {diff.text.removed.map((line) => (
            <p key={line} className="m-0 pl-3 text-failed line-through">
              {line}
            </p>
          ))}
        </div>
      )}
      {/* The whole text, the sentences added marked. */}
      <div className="flex flex-col gap-1">
        {sentencesOf(content.text).map((line, index) => (
          <p key={index} className="m-0">
            {line.map((piece, at) => (
              <span key={at} className={added.has(piece.trim()) ? "rounded-sm bg-added" : ""}>
                {piece}
              </span>
            ))}
          </p>
        ))}
      </div>
      <h3 className="m-0 text-lead">{t("draft.full.labels")}</h3>
      <ul className="m-0 flex flex-col gap-1 pl-5">
        {content.label_definitions.map((d) => {
          const mark = labelMark(diff, d.name);
          return (
            <li key={d.name}>
              <b>{d.name}</b>
              {d.parent && ` ⊂ ${d.parent}`} · {t(`shape.${d.shape}`)}
              {d.attributes.length > 0 && ` · ${d.attributes.map((a) => a.name).join(", ")}`}
              {mark && (
                <span className="ml-2 rounded-sm bg-added px-1 text-xs">
                  {t(`draft.mark.${mark}`)}
                </span>
              )}
              {d.description && <span className="text-muted-foreground"> — {d.description}</span>}
            </li>
          );
        })}
        {diff?.removed.map((name) => (
          <li key={name} className="text-failed line-through">
            {name}
          </li>
        ))}
      </ul>
    </section>
  );
}
