// The gallery as a table (step 13 design 1): one row per object of the view, children under
// their parent, the attribute values as columns. Sorting and finding (text, empty values, values
// found more than once) work on these rows.
import type { Badge, GalleryItem, PutLabel, View } from "@/api/types";
import { byLabel } from "./display";

export interface Row {
  key: string;
  imageId: string;
  imageName: string;
  annotationId: string | null;
  label: string;
  number: number | null;
  /** "label number" of the parent, "" for none. */
  parent: string;
  depth: number;
  values: Record<string, string>;
}

export type Mode = "all" | "empty" | "same";

/** The attribute columns of images judged by a plan: its labels' attributes in its order, then
 * any other found on the objects (another plan's results). labels: the plan's (usePlanLabels);
 * null: no plan, the ones found (definition 85; user 2026-10-30: an attribute none had a value
 * of yet had no column, so the missing values were not seen). */
export function attributeColumns(items: GalleryItem[], labels: PutLabel[] | null): string[] {
  const seen: string[] = [];
  const add = (name: string) => {
    if (!seen.includes(name)) seen.push(name);
  };
  for (const label of labels ?? []) for (const name of label.attributes ?? []) add(name);
  for (const item of items)
    for (const a of item.annotations) for (const name of Object.keys(a.attributes ?? {})) add(name);
  return seen;
}

export function buildRows(items: GalleryItem[]): Row[] {
  const rows: Row[] = [];
  for (const item of items) {
    const annotations = item.annotations;
    if (annotations.length === 0) {
      rows.push({
        key: item.image.id,
        imageId: item.image.id,
        imageName: item.image.name,
        annotationId: null,
        label: "",
        number: null,
        parent: "",
        depth: 0,
        values: {},
      });
      continue;
    }
    const byId = new Map(annotations.map((a) => [a.id, a]));
    const name = (id: string | null) => {
      const a = id ? byId.get(id) : undefined;
      return a ? `${a.label} ${a.number ?? ""}`.trim() : "";
    };
    // Parents first, each followed by its children (deeper indent), in number order.
    const order = (a: { number?: number | null }, b: { number?: number | null }) =>
      (a.number ?? 1e9) - (b.number ?? 1e9);
    const place = (parentId: string | null, depth: number) => {
      const level = annotations
        .filter((a) => (a.parent_id && byId.has(a.parent_id) ? a.parent_id : null) === parentId)
        .sort((a, b) => byLabel(a.label, b.label) || order(a, b));
      for (const a of level) {
        rows.push({
          // With the image: the id alone repeated across images (a result sample's objects were
          // numbered s-0, s-1… in every image) and the table kept stale rows (Astra 2026-10-07).
          key: `${item.image.id}/${a.id}`,
          imageId: item.image.id,
          imageName: item.image.name,
          annotationId: a.id,
          label: a.label,
          number: a.number ?? null,
          parent: name(a.parent_id),
          depth,
          values: Object.fromEntries(
            // A value not read is shown as nothing, as an absent one is (Astra 2026-10-15: a
            // sample's "null" and a result without the field read as two things).
            Object.entries(a.attributes ?? {})
              .filter(([, v]) => v !== null && v !== undefined && v !== "")
              .map(([k, v]) => [k, String(v)]),
          ),
        });
        place(a.id, depth + 1);
      }
    };
    place(null, 0);
  }
  return rows;
}

/** The attributes each label has, the plan's and any seen on its objects: an empty value counts
 * only in these, other columns are not that label's (found 2026-10-05 by Sol: "has an empty
 * value" kept rows for attributes their label never has). */
export function labelColumns(rows: Row[], labels: PutLabel[] | null): Map<string, Set<string>> {
  const found = new Map<string, Set<string>>();
  for (const label of labels ?? []) found.set(label.name, new Set(label.attributes ?? []));
  for (const row of rows) {
    const set = found.get(row.label) ?? new Set<string>();
    for (const name of Object.keys(row.values)) set.add(name);
    found.set(row.label, set);
  }
  return found;
}

/** Rows that hold the words, and with mode "empty" an empty value of an attribute of its own
 * label, "same" a value that another row also has in the same column. */
export function findRows(
  rows: Row[],
  text: string,
  mode: Mode,
  columns: string[],
  labels: PutLabel[] | null,
): Row[] {
  const words = text.toLowerCase().split(/\s+/).filter(Boolean);
  const counts = new Map<string, number>();
  for (const row of rows)
    for (const c of columns) {
      const v = row.values[c];
      if (v) counts.set(`${c}\u0000${v}`, (counts.get(`${c}\u0000${v}`) ?? 0) + 1);
    }
  const own = labelColumns(rows, labels);
  return rows.filter((row) => {
    const cells = [row.imageName, row.label, row.parent, ...Object.values(row.values)]
      .join(" ")
      .toLowerCase();
    if (!words.every((w) => cells.includes(w))) return false;
    if (mode === "empty")
      return (
        row.annotationId !== null &&
        columns.some((c) => own.get(row.label)?.has(c) && !row.values[c])
      );
    if (mode === "same")
      return columns.some((c) => (counts.get(`${c}\u0000${row.values[c]}`) ?? 0) > 1);
    return true;
  });
}

/** Sorted by a column ("image", "label", "number", "parent", "status" or an attribute). */
export function sortRows(rows: Row[], column: string | null, up: boolean): Row[] {
  if (!column) return rows;
  const value = (row: Row): string | number =>
    column === "image"
      ? row.imageName
      : column === "label"
        ? row.label
        : column === "number"
          ? (row.number ?? -1)
          : column === "parent"
            ? row.parent
            : (row.values[column] ?? "");
  return [...rows].sort((a, b) => {
    const x = value(a);
    const y = value(b);
    const c =
      typeof x === "number" && typeof y === "number"
        ? x - y
        : String(x).localeCompare(String(y), "ja", { numeric: true });
    return up ? c : -c;
  });
}

/** The image shows an annotation: the one it has now (kind "result"), or a made result. */
export function hasAnswer(badge: Badge): boolean {
  return badge.kind === "result" || Boolean(badge.succeeded);
}

/** No answer to show (stopped, not in the run, nothing adopted): "no result", not "0 objects"
 * (Astra 2026-10-06: "—", "no objects" and "objects (0)" for the same stopped image). A left
 * out image with the result it would use has one, if with no objects (Astra 2026-10-17 P07: the
 * table said "no result", the list of objects "annotated, none"). */
export function noAnswer(item: GalleryItem, view: View): boolean {
  if (item.badge.kind === "excluded" && item.badge.result_id) return false;
  return view !== "images" && !item.annotations.length && !hasAnswer(item.badge);
}
