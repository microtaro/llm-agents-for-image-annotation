// What a person can do with the image in the loupe (step 7 design 1): choose its result as its
// image's reference (definition 38.1), and what finishing a fix does once one was made (the result
// is fixed on the image itself, user 2026-10-27). Taking images out of the dataset is the
// gallery's (user 2026-10-14).
import type { ReactNode } from "react";
import { ReferenceChoice } from "@/components/ReferenceChoice";
import { t } from "@/i18n";

export function LoupeActions({
  reference,
  children = null,
}: {
  /** The result shown, to choose as its image's reference (definition 38.1). */
  reference?: { datasetId: string; imageId: string; resultId: string };
  /** Said first: what finishing the fix does, or why the result cannot be fixed. */
  children?: ReactNode;
}) {
  // Taking images out of the dataset is the gallery's, with adding them (user 2026-10-14: the
  // loupe could take out but not add).
  if (!reference && !children) return null;
  return (
    <section className="flex flex-col gap-2 border-b border-line px-4.5 py-3">
      <h2 className="m-0 text-heading">{t("loupe.actions")}</h2>
      {children}
      {reference && (
        <div className="flex flex-wrap gap-2">
          <ReferenceChoice {...reference} />
        </div>
      )}
    </section>
  );
}
