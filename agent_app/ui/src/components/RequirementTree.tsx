// The requirement and an image's annotation drawn as one tree (definition 25.2-19, 26.7): the
// root, each label (a child label indented under its parent, "inside" it) and its attributes,
// with what each attribute takes, or an object's values. A row's mark says how it differs, in
// words and signs, not colors (memory "visual needs grounds"); a label's swatch is its color.
import type { LabelDefinition } from "@/api/types";
import { DESCRIPTION_LINES, FoldText } from "@/components/FoldText";
import { t } from "@/i18n";
import type { Mark, TreeRow } from "@/lib/requirementTree";

function what(row: TreeRow): string {
  if (row.value !== undefined)
    return row.value === null || row.value === "" ? t("tree.empty") : String(row.value);
  if (row.kind === "label") return row.folded ? t("tree.folded") : row.path ? "" : t("tree.any");
  if (!row.attribute) return "";
  return row.attribute.type === "choice"
    ? t("tree.type.choice", { choices: (row.attribute.choices ?? []).join(t("tree.choices.join")) })
    : t(`tree.type.${row.attribute.type}`);
}

export function RequirementTree({
  rows,
  root,
  colors,
  definitions = [],
  only,
  descriptions,
}: {
  rows: TreeRow[];
  /** The root's words: the image as a whole, or the image whose annotation it is. */
  root: string;
  colors: Record<string, string>;
  /** The labels' parents, for an object in none of its parent's objects. */
  definitions?: LabelDefinition[];
  /** The words of an "only" mark ("only requirement 1"). */
  only?: string;
  /** Each label's description, under its row (the plan's screen, user 2026-11-10: the person
   * could not see what the worker AI reads of a label). Left out where rows of cards side by
   * side must keep their heights. */
  descriptions?: Record<string, string>;
}) {
  const markText: Record<Mark, string> = {
    same: t("tree.mark.same"),
    add: t("tree.mark.add"),
    drop: t("tree.mark.drop"),
    only: only ?? "",
  };
  return (
    <div className="flex flex-col text-body" role="list">
      {rows.map((row, index) => {
        if (row.kind === "root")
          return (
            <div key={index} role="listitem" className="py-0.5 font-semibold text-muted-foreground">
              {root}
            </div>
          );
        const indent = { paddingLeft: `${(row.depth - 1) * 1.1}em` };
        if (row.blank)
          return (
            // Kept so the cards beside it stay aligned (memory "align and leave blank").
            <div key={index} aria-hidden="true" className="invisible border-b border-line py-0.5">
              {row.name}
            </div>
          );
        const parent = definitions.find((d) => d.name === row.label)?.parent;
        return (
          <div
            key={index}
            role="listitem"
            className={`grid grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_auto] items-baseline gap-2 border-b border-line py-0.5 last:border-b-0 ${row.mark === "drop" ? "text-muted-foreground line-through" : ""}`}
          >
            <span className="min-w-0 truncate" style={indent} title={row.name}>
              {row.depth > 1 && <span className="text-muted-foreground no-underline">└ </span>}
              {row.kind === "label" ? (
                <>
                  <span
                    aria-hidden="true"
                    className="mr-1 inline-block size-2.5 rounded-[2px] border-2 align-[-1px]"
                    style={{ borderColor: colors[row.name] ?? "#4363D8" }}
                  />
                  <b>
                    {row.path ? `${row.path} ` : ""}
                    {row.name}
                  </b>
                  {row.shape && ` ${t(`tree.shape.${row.shape}`)}`}
                  {row.inside && (
                    <span className="ml-1.5 rounded-sm border border-line px-1 text-note text-muted-foreground">
                      {t("tree.inside", { label: row.inside })}
                    </span>
                  )}
                  {row.outside && parent && (
                    <span className="ml-1.5 text-note text-muted-foreground">
                      {t("tree.outside", { label: parent })}
                    </span>
                  )}
                </>
              ) : (
                row.name
              )}
            </span>
            <span className="min-w-0 truncate text-muted-foreground" title={what(row)}>
              {what(row)}
            </span>
            {row.mark ? (
              <span className="justify-self-end whitespace-nowrap rounded-sm border border-line px-1.5 text-note">
                {markText[row.mark]}
              </span>
            ) : (
              <span />
            )}
            {row.kind === "label" && !row.path && descriptions?.[row.name]?.trim() && (
              // Indented as one, so "Show all" starts where the text does (2026-11-10: it stood
              // 12 px to the left of a long description).
              <div
                className="col-span-3"
                style={{ paddingLeft: `calc(${indent.paddingLeft} + 1.1em)` }}
              >
                <FoldText lines={DESCRIPTION_LINES} className="text-note text-muted-foreground">
                  <p className="m-0 whitespace-pre-wrap">{descriptions[row.name]}</p>
                </FoldText>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
