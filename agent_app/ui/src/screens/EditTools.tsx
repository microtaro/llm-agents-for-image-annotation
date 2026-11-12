// The row above an edited image and its keys, shared by the master and the reference editors:
// the label for new objects, add a box or a polygon, delete, undo, and a hint for the tool.
import { type ReactNode, useEffect } from "react";
import type { LabelDefinition } from "@/api/types";
import { Pentagon, Square, Trash2, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import type { Tool } from "./EditCanvas";

export function EditTools({
  definitions,
  label,
  onLabel,
  tool,
  onTool,
  anyShape = false,
  canDelete,
  onDelete,
  canUndo,
  onUndo,
  onAddWhole,
  after = null,
  eye = null,
}: {
  definitions: LabelDefinition[];
  label: string;
  onLabel: (label: string) => void;
  tool: Tool;
  onTool: (tool: Tool) => void;
  /** A reference may draw a label in either shape (DESIGN.md 6); a master only in its own. */
  anyShape?: boolean;
  canDelete: boolean;
  onDelete: () => void;
  canUndo: boolean;
  onUndo: () => void;
  /** A label of the whole image (VQA): add its answer without drawing. */
  onAddWhole?: () => void;
  /** After undo, apart: the fix's "stop" (back to before fixing), the other way back. */
  after?: ReactNode;
  /** At the row's right end, right over the image: how it looks (user 2026-10-28, as every
   * list's head). */
  eye?: ReactNode;
}) {
  const shape = definitions.find((d) => d.name === label)?.shape;
  const toggle = (next: Tool) => (
    <Button
      aria-pressed={tool === next}
      disabled={!label || (!anyShape && shape !== next)}
      onClick={() => onTool(tool === next ? "select" : next)}
      className={tool === next ? "border-action outline-2 outline-action" : ""}
    >
      {next === "bbox" ? (
        <Square className="size-4" aria-hidden />
      ) : (
        <Pentagon className="size-4" aria-hidden />
      )}
      {t(next === "bbox" ? "edit.addBox" : "edit.addPolygon")}
    </Button>
  );
  // Kinds of tool apart, each with its icon (user 2026-10-14: a label list, adding, deleting
  // and undoing in one row of words read as one thing; undo was in the label's place).
  const group =
    "flex flex-wrap items-center gap-1.5 rounded-md border border-line bg-surface px-2 py-1";
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-line bg-sheet px-5 py-2">
      {/* No heading: the buttons say what is added (user 2026-10-28: "add" before "label" read
          as adding a label, and the buttons said "add" again); the chosen one's group keeps its
          heading, as "delete" alone does not say what goes. */}
      <div role="group" aria-label={t("edit.group.add")} className={group}>
        <label className="flex items-center gap-1.5 text-body">
          {t("edit.group.add.label")}
          <select
            className="rounded-md border border-line bg-surface px-2 py-1"
            value={label}
            onChange={(e) => onLabel(e.target.value)}
          >
            {definitions.map((d) => (
              <option key={d.name} value={d.name}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        {shape === "image" && onAddWhole ? (
          <Button onClick={onAddWhole}>{t("edit.addAnswer")}</Button>
        ) : (
          <>
            {toggle("bbox")}
            {toggle("polygon")}
          </>
        )}
      </div>
      <div role="group" aria-label={t("edit.group.chosen")} className={group}>
        <span className="text-small text-muted-foreground">{t("edit.group.chosen")}</span>
        {/* Deleting is red wherever its entry is (Astra 2026-10-06). */}
        <Button className="text-failed" disabled={!canDelete} onClick={onDelete}>
          <Trash2 className="size-4" aria-hidden />
          {t("common.delete")}
        </Button>
      </div>
      {/* Undo is of every change (a box made bigger too), so a group of its own, but right beside
          the tools (user 2026-10-16: at the far end it read as apart from editing). */}
      <Button disabled={!canUndo} onClick={onUndo}>
        <Undo2 className="size-4" aria-hidden />
        {t("edit.undo")}
      </Button>
      {after && <span className="ml-4">{after}</span>}
      {eye && (
        <>
          <span className="flex-1" />
          {eye}
        </>
      )}
      {/* Two lines kept for the hint, so changing the tool never moves the image. */}
      <span className="line-clamp-2 min-h-[3.2em] basis-full text-xs leading-[1.6] text-muted-foreground">
        {t(`edit.hint.${tool}`)}
      </span>
    </div>
  );
}

/** Delete (or Backspace while selecting) removes the chosen object; Ctrl+Z undoes. */
export function useEditKeys(
  selected: string | null,
  tool: Tool,
  remove: () => void,
  undo: () => void,
) {
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      const typing = (event.target as HTMLElement).closest("input, textarea, select");
      if (typing) return;
      if (
        (event.key === "Delete" || (event.key === "Backspace" && tool === "select")) &&
        selected
      ) {
        event.preventDefault();
        remove();
      }
      if (event.key === "z" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        undo();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [selected, tool, remove, undo]);
}
