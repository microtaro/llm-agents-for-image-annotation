// The loupe's image when its result can be fixed (types design 7.1, from the master editor of
// step 7): looked at and fixed on one image (user 2026-10-27: zoomed in to look, then a second
// screen to fix, zoomed out again). Nothing is a fix until something is changed; every change is
// kept on the server as it is made. There is no saving (user 2026-10-16, as for the plan and
// training): finishing (closing, the next image, leaving) records the fix as one more annotation
// record, a person's, which training then uses; "stop" goes back to before fixing; the notice
// takes a recorded fix back. The loupe's side shows its objects and what finishing does.
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import type { Annotation, LabelDefinition } from "@/api/types";
import { LabelDot } from "@/components/LabelColors";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { invalidate } from "@/lib/useApi";
import { type EditShape, nameOf, nested, remember, unchanged } from "@/lib/editing";
import { EditCanvas, type Tool } from "./EditCanvas";
import { EditTools, useEditKeys } from "./EditTools";
import { ObjectForm } from "./ObjectForm";
import { errorText } from "@/lib/errorText";
import { showInSide } from "@/lib/panelScroll";

interface Draft {
  from_result_id: string;
  annotations: {
    number?: number | null;
    ref: string;
    label: string;
    geometry: EditShape["geometry"];
    parent: string | null;
    attributes: Record<string, string | number>;
  }[];
  written_by: string;
  updated_at: string;
}

const fromBase = (a: Annotation): EditShape => ({
  id: a.id,
  label: a.label,
  geometry: a.geometry,
  attributes: a.attributes ?? {},
  parent: a.parent_id,
  changed: false,
  number: a.number ?? null,
});

/** Shapes made or changed against the base (drawn dashed). */
export function markChanged(shapes: EditShape[], base: Annotation[]): EditShape[] {
  const original = new Map(base.map((a) => [a.id, a]));
  return shapes.map((shape) => {
    const was = original.get(shape.id);
    return { ...shape, changed: !(was !== undefined && unchanged(was, shape)) };
  });
}

/** What the editor puts in the loupe's side: the objects as they are now, and what finishing
 * does once something was changed. */
export interface FixSlots {
  objects: ReactNode;
  note: ReactNode;
}

export function ResultEditor({
  datasetId,
  imageId,
  width,
  height,
  resultId,
  annotations,
  definitions,
  colors,
  chosen: first = null,
  used = false,
  overlay = null,
  onChanged,
  side,
  eye,
}: {
  datasetId: string;
  imageId: string;
  width: number;
  height: number;
  /** The result shown, that a fix starts from (a draft left from before keeps its own). */
  resultId: string;
  /** Its annotations, what a change is told against. */
  annotations: Annotation[];
  definitions: LabelDefinition[];
  colors: Record<string, string>;
  /** The object chosen before editing (from the table), chosen here too. */
  chosen?: string | null;
  /** The image is used for training now: the fix replaces what training uses (said before). */
  used?: boolean;
  /** The mark over the image, as on its card. */
  overlay?: ReactNode;
  /** Whether something was changed (a fix to record), for the loupe's top row. */
  onChanged?: (changed: boolean) => void;
  /** The loupe's side, given the editor's parts. */
  side: (slots: FixSlots) => ReactNode;
  /** How it looks, at the tools' row's right end right over the image. */
  eye?: ReactNode;
}) {
  const path = `/v1/datasets/${datasetId}/images/${imageId}/drafts/fix`;
  // The result and annotations a fix is told against: read when a change is made, not a reason
  // to read the draft again (the gallery's page is read again while a person looks).
  const base = useRef({ resultId, annotations });
  base.current = { resultId: base.current.resultId, annotations };
  const fresh = () => annotations.map(fromBase);
  const [shapes, setShapes] = useState<EditShape[]>([]);
  const [history, setHistory] = useState<EditShape[][]>([]);
  // Astra 2026-10-05: the field chosen in the table was not chosen any more when editing.
  const [selected, setSelected] = useState<string | null>(first);
  // A row of the table chosen while the image is open chooses here too.
  useEffect(() => setSelected(first), [first]);
  const [tool, setTool] = useState<Tool>("select");
  const [label, setLabel] = useState(definitions[0]?.name ?? "");
  const [, setDraft] = useState<{ who: string; at: string } | null>(null);
  // Something to record on finishing: a change made here, or a draft left from before.
  const touched = useRef(false);
  // The same, for the way out's words: nothing changed, it only ends fixing.
  const [dirty, setDirty] = useState(false);
  const pending = useRef<number | null>(null);
  const unsent = useRef<EditShape[] | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  useEffect(() => onChanged?.(dirty), [dirty, onChanged]);

  useEffect(() => {
    api<Draft | null>(path)
      .then((found) => {
        if (!found) {
          setShapes(fresh());
          return;
        }
        // A draft left from before goes on from the result it started from.
        base.current = { ...base.current, resultId: found.from_result_id };
        const loaded = found.annotations.map((a) => ({
          id: a.ref,
          label: a.label,
          geometry: a.geometry,
          attributes: a.attributes ?? {},
          parent: a.parent,
          changed: false,
          number: a.number ?? null,
        }));
        setShapes(markChanged(loaded, base.current.annotations));
        setDraft({ who: found.written_by, at: found.updated_at });
        touched.current = true;
        setDirty(true);
      })
      .catch((reason) => {
        toast.error(errorText(reason));
        setShapes(fresh());
      });
    // Read once for the image (path); the annotations read again are told against (base).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  const send = useCallback(
    (next: EditShape[]) => {
      // Written only once the server took it (a refused write stays unsent; see InstructionPanel).
      return api<Draft>(path, {
        method: "PUT",
        body: {
          from_result_id: base.current.resultId,
          annotations: next.map((s) => ({
            number: s.number ?? null,
            ref: s.id,
            label: s.label,
            geometry: s.geometry,
            parent: s.parent,
            attributes: s.attributes,
          })),
        },
      }).then((saved) => {
        if (unsent.current === next) unsent.current = null;
        setRefused(null);
        setDraft({ who: saved.written_by, at: saved.updated_at });
      });
    },
    [path],
  );

  const commit = useCallback(
    (next: EditShape[]) => {
      touched.current = true;
      setDirty(true);
      setHistory((past) => remember(past, shapes));
      const marked = markChanged(next, base.current.annotations);
      setShapes(marked);
      unsent.current = marked;
      if (pending.current) window.clearTimeout(pending.current);
      pending.current = window.setTimeout(() => {
        pending.current = null;
        send(marked).catch((reason: Error) => {
          setRefused(errorText(reason));
          toast.error(t("fix.draft.refused", { message: errorText(reason) }));
        });
      }, 600);
    },
    [shapes, send],
  );

  const remove = useCallback(() => {
    if (!selected) return;
    commit(
      shapes
        .filter((s) => s.id !== selected)
        .map((s) => (s.parent === selected ? { ...s, parent: null } : s)),
    );
    setSelected(null);
  }, [selected, shapes, commit]);

  const undo = useCallback(() => {
    const last = history[history.length - 1];
    if (!last) return;
    setHistory(history.slice(0, -1));
    setShapes(last);
    // The change undone may still wait to be written; it must not overwrite the undo (found
    // 2026-10-05 by Sol: Delete, Ctrl+Z, Save saved the deleted state).
    if (pending.current) window.clearTimeout(pending.current);
    pending.current = null;
    unsent.current = last;
    send(last).catch((reason: Error) => toast.error(errorText(reason)));
  }, [history, send]);

  useEditKeys(selected, tool, remove, undo);
  // The list follows a choice made on the image (Astra 2026-10-06: it stayed where it was).
  useEffect(() => {
    if (selected) showInSide(document.querySelector(`[data-object="${CSS.escape(selected)}"]`));
  }, [selected]);

  // Finishing records the fix (user 2026-10-16: no saving to remember; closing, the next
  // image or leaving ends it). Kept in refs, as it runs when the editor goes away.
  const finish = useRef<() => void>(() => undefined);
  finish.current = () => {
    if (!touched.current) return;
    const path_ = path;
    const last = unsent.current;
    if (pending.current) window.clearTimeout(pending.current);
    void (async () => {
      try {
        if (last) await send(last);
        const made = await api<{ before: string }>(`${path_}/save`, { body: {} });
        invalidate(datasetId);
        toast.success(t(used ? "fix.recorded.used" : "fix.recorded"), {
          // Long enough to take back (the usual notice went before it could be pressed).
          duration: 10000,
          action: {
            label: t("select.undo"),
            // Taken back: the result used before the fix is chosen again (definition 19.2);
            // the fix stays as a record.
            onClick: () =>
              void api(`/v1/datasets/${datasetId}/images/${imageId}/switch`, {
                body: { result_id: made.before },
              })
                .then(() => invalidate(datasetId))
                .catch((reason) => toast.error(errorText(reason))),
          },
        });
      } catch (reason) {
        toast.error(errorText(reason));
      }
    })();
  };
  useEffect(() => () => finish.current(), []);

  async function stop() {
    // Back to before fixing, nothing recorded; looking and fixing go on from there.
    if (pending.current) window.clearTimeout(pending.current);
    pending.current = null;
    unsent.current = null;
    touched.current = false;
    await api(path, { method: "DELETE" }).catch((reason) => toast.error(errorText(reason)));
    base.current = { resultId, annotations };
    setShapes(fresh());
    setHistory([]);
    setSelected(null);
    setRefused(null);
    setDirty(false);
  }

  const names = numberShapes(shapes);
  const chosen = shapes.find((s) => s.id === selected);

  // Stopping goes back to before fixing (user 2026-10-14, beside undo and apart from it, user
  // 2026-10-16); shown once something was changed, there being nothing to stop before.
  const exit = dirty ? <Button onClick={() => void stop()}>{t("fix.stop")}</Button> : null;

  const objects = (
    <section className="flex flex-col gap-2 border-b border-line px-4.5 py-3">
      {chosen ? (
        <section className="flex flex-col gap-2 rounded-md border border-line bg-surface p-2.5">
          <strong className="text-body">{names[chosen.id]}</strong>
          <ObjectForm
            shape={chosen}
            shapes={shapes}
            definitions={definitions}
            names={names}
            onChange={(next) => commit(shapes.map((s) => (s.id === next.id ? next : s)))}
          />
        </section>
      ) : (
        <p className="m-0 text-body text-muted-foreground">{t("fix.select.hint")}</p>
      )}
      <details open>
        <summary className="cursor-pointer font-semibold">
          {t("loupe.objects", { count: shapes.length })}
        </summary>
        <ol className="m-0 mt-1.5 flex flex-col gap-0.5 pl-5 text-body">
          {nested(shapes).map(({ shape: s, depth }) => (
            <li key={s.id} style={{ marginLeft: `${depth * 1.25}rem` }}>
              <button
                type="button"
                data-object={s.id}
                onClick={() => setSelected(s.id === selected ? null : s.id)}
                className={`cursor-pointer rounded-sm px-0.5 text-left ${s.id === selected ? "bg-selected font-semibold text-selected-ink" : ""}`}
              >
                <LabelDot color={colors[s.label]} />
                {names[s.id]}
                {Object.entries(s.attributes)
                  .filter(([, value]) => value !== null && value !== undefined && value !== "")
                  .map(([name, value]) => ` · ${name} ${value}`)}
                {s.changed ? ` ${t("fix.changed")}` : ""}
              </button>
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
  // What finishing does, said once something was changed (user 2026-10-16: training uses it).
  const note =
    dirty || refused ? (
      <div className="flex flex-col gap-2">
        {dirty && (
          <p className="m-0 rounded-md border border-processing bg-surface px-2.5 py-1.5 text-body">
            {t(used ? "fix.finish.used" : "fix.finish.unused")}
          </p>
        )}
        {refused && (
          <p className="m-0 text-body text-failed">{t("draft.unsent", { message: refused })}</p>
        )}
      </div>
    ) : null;

  return (
    <div className="flex flex-1 flex-wrap">
      <main className="flex min-w-0 flex-[999_1_420px] flex-col">
        <EditTools
          after={exit}
          eye={eye}
          definitions={definitions}
          label={label}
          onLabel={setLabel}
          tool={tool}
          onTool={setTool}
          canDelete={Boolean(selected)}
          onDelete={remove}
          canUndo={history.length > 0}
          onUndo={undo}
          onAddWhole={() => {
            // A whole-image answer is kept as a box over the image (step 13 design 3).
            const id = `new-${crypto.randomUUID()}`;
            commit([
              ...shapes,
              {
                id,
                label,
                geometry: { type: "bbox", xywh: [0, 0, width, height] },
                attributes: {},
                parent: null,
                changed: true,
              },
            ]);
            setSelected(id);
          }}
        />
        <EditCanvas
          imageId={imageId}
          width={width}
          height={height}
          shapes={shapes}
          colors={colors}
          selected={selected}
          tool={tool}
          onSelect={setSelected}
          onCommit={(id, shape) => commit(shapes.map((s) => (s.id === id ? shape : s)))}
          onAdd={(geometry) => {
            const id = `new-${crypto.randomUUID()}`;
            commit([
              ...shapes,
              { id, label, geometry, attributes: {}, parent: null, changed: true },
            ]);
            setSelected(id);
          }}
          onToolDone={() => setTool("select")}
          overlay={overlay}
        />
      </main>
      {side({ objects, note })}
    </div>
  );
}

/** "circle 7" by the server's number; a new object is "circle (new)" until saved. */
export function numberShapes(shapes: EditShape[]): Record<string, string> {
  return Object.fromEntries(shapes.map((s) => [s.id, nameOf(s.label, s.number, t("object.new"))]));
}
