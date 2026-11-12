// One tree for the requirement and for an image's annotation (definition 25.2-19, 26.7): the
// requirement is the image's form (its labels, each with its attributes, a label inside its
// parent label); an annotation repeats it for each object, numbered by its path in the tree
// (1, 1-2). Cards compared side by side keep their rows aligned: every card has the rows of all
// of them, the ones it lacks left blank (memory "align and leave blank").
import type { Annotation, AttributeDefinition, LabelDefinition } from "@/api/types";
import { boundsOf } from "./boxes";

/** How a row differs: from the plan before (same, add, drop), or what only this card has. */
export type Mark = "same" | "add" | "drop" | "only";

export interface TreeRow {
  kind: "root" | "label" | "attr";
  depth: number;
  name: string;
  /** A label row's label (its color); an attribute row's label. */
  label?: string;
  shape?: LabelDefinition["shape"];
  /** The label it is inside (a child label of the form). */
  inside?: string | null;
  attribute?: Pick<AttributeDefinition, "type" | "choices">;
  /** An answer's value of the attribute (null: not read). */
  value?: string | number | null;
  /** An object's path in the tree (1, 1-2). */
  path?: string;
  /** An object of a child label in no object of its parent label. */
  outside?: boolean;
  /** An object whose insides are not listed (the cards beside each other stay short). */
  folded?: boolean;
  mark?: Mark;
  /** Kept only to align the rows of cards side by side. */
  blank?: boolean;
}

/** The labels of several forms, each with all their attributes, in the order they come. */
export interface Union {
  labels: { name: string; parent: string | null; attributes: string[] }[];
}

export function unionOf(forms: LabelDefinition[][]): Union {
  const labels: Union["labels"] = [];
  for (const form of forms)
    for (const d of form) {
      let found = labels.find((l) => l.name === d.name);
      if (!found) labels.push((found = { name: d.name, parent: d.parent, attributes: [] }));
      for (const a of d.attributes)
        if (!found.attributes.includes(a.name)) found.attributes.push(a.name);
    }
  return { labels };
}

const top = (names: Set<string>, parent: string | null) => !parent || !names.has(parent);

/** The requirement's rows: the root, each label (a child under its parent) and its attributes.
 * base: the plan before (marks same, add, drop); others: the cards beside it (an attribute none
 * of them has is marked only); union: the rows of all cards (the ones this lacks blank). */
export function schemaRows(
  definitions: LabelDefinition[],
  options: { base?: LabelDefinition[]; others?: LabelDefinition[][]; union?: Union } = {},
): TreeRow[] {
  const { base, others, union } = options;
  const byName = new Map(definitions.map((d) => [d.name, d]));
  const before = base ? new Map(base.map((d) => [d.name, d])) : null;
  // The labels of the union first (aligned with the cards beside), then this one's own.
  const own = unionOf(base ? [base, definitions] : [definitions]).labels;
  const order: Union["labels"] = union
    ? [...union.labels, ...own.filter((l) => !union.labels.some((u) => u.name === l.name))]
    : own;
  const names = new Set(order.map((l) => l.name));
  const rows: TreeRow[] = [{ kind: "root", depth: 0, name: "" }];
  const mark = (here: boolean, there: boolean | null): Mark | undefined =>
    there === null ? undefined : here && there ? "same" : here ? "add" : "drop";
  const walk = (entry: Union["labels"][number], depth: number) => {
    const d = byName.get(entry.name);
    const old = before?.get(entry.name);
    if (!d && !old) {
      rows.push({ kind: "label", depth, name: entry.name, blank: true });
      for (const a of entry.attributes)
        rows.push({ kind: "attr", depth: depth + 1, name: a, blank: true });
    } else {
      const shown = (d ?? old) as LabelDefinition;
      rows.push({
        kind: "label",
        depth,
        name: entry.name,
        label: entry.name,
        shape: shown.shape,
        inside: shown.parent && names.has(shown.parent) ? shown.parent : null,
        mark: mark(Boolean(d), before ? Boolean(old) : null),
      });
      for (const name of entry.attributes) {
        const here = d?.attributes.find((a) => a.name === name);
        const there = old?.attributes.find((a) => a.name === name);
        if (!here && !there) {
          rows.push({ kind: "attr", depth: depth + 1, name, blank: true });
          continue;
        }
        const alone =
          others && here
            ? !others.some((form) =>
                form.some(
                  (o) => o.name === entry.name && o.attributes.some((a) => a.name === name),
                ),
              )
            : false;
        const shownAttr = (here ?? there) as AttributeDefinition;
        rows.push({
          kind: "attr",
          depth: depth + 1,
          name,
          label: entry.name,
          attribute: { type: shownAttr.type, choices: shownAttr.choices },
          mark: alone ? "only" : mark(Boolean(here), before ? Boolean(there) : null),
        });
      }
    }
    for (const child of order.filter((l) => l.parent === entry.name)) walk(child, depth + 1);
  };
  for (const entry of order.filter((l) => top(names, l.parent))) walk(entry, 1);
  return rows;
}

type Placed = Pick<Annotation, "id" | "label" | "geometry" | "attributes" | "parent_id">;

/** Each object's parent: the one it names, else the smallest object of its label's parent
 * label that holds its middle; null for none. */
export function parentsOf(
  objects: Placed[],
  definitions: LabelDefinition[],
): Map<string, string | null> {
  const parentLabel = new Map(definitions.map((d) => [d.name, d.parent]));
  const ids = new Set(objects.map((o) => o.id));
  const area = (o: Placed) => {
    const [, , w, h] = boundsOf(o.geometry);
    return w * h;
  };
  const found = new Map<string, string | null>();
  for (const o of objects) {
    if (o.parent_id && ids.has(o.parent_id)) {
      found.set(o.id, o.parent_id);
      continue;
    }
    const label = parentLabel.get(o.label);
    if (!label) {
      found.set(o.id, null);
      continue;
    }
    const [x, y, w, h] = boundsOf(o.geometry);
    const cx = x + w / 2;
    const cy = y + h / 2;
    const holding = objects
      .filter((p) => p.label === label && p.id !== o.id)
      .filter((p) => {
        const [px, py, pw, ph] = boundsOf(p.geometry);
        return cx >= px && cx <= px + pw && cy >= py && cy <= py + ph;
      })
      .sort((a, b) => area(a) - area(b));
    found.set(o.id, holding[0]?.id ?? null);
  }
  return found;
}

/** An image's annotation as the requirement's tree repeated for each object: its rows and each
 * object's path (the tags over the image say it too). union: the attributes of the cards beside
 * it (the ones its label lacks blank); folded: past the first object, only each one's line. */
export function answerRows(
  objects: Placed[],
  definitions: LabelDefinition[],
  options: { union?: Union; folded?: boolean } = {},
): { rows: TreeRow[]; paths: Map<string, string> } {
  const parents = parentsOf(objects, definitions);
  const attrs = new Map(definitions.map((d) => [d.name, d.attributes]));
  const withParentLabel = new Set(definitions.filter((d) => d.parent).map((d) => d.name));
  const rows: TreeRow[] = [{ kind: "root", depth: 0, name: "" }];
  const paths = new Map<string, string>();
  const attributeRows = (o: Placed, depth: number): TreeRow[] => {
    const own = attrs.get(o.label) ?? [];
    const names =
      options.union?.labels.find((l) => l.name === o.label)?.attributes ?? own.map((a) => a.name);
    return names.map((name) => {
      const a = own.find((x) => x.name === name);
      return a
        ? {
            kind: "attr",
            depth,
            name,
            label: o.label,
            attribute: { type: a.type, choices: a.choices },
            value: o.attributes[name] ?? null,
          }
        : { kind: "attr", depth, name, blank: true };
    });
  };
  // In the plan's order of labels (a box before the marks in it), each label's in its order.
  const rank = new Map(definitions.map((d, index) => [d.name, index]));
  const ordered = (list: Placed[]) =>
    list
      .map((o, index) => ({ o, index }))
      .sort(
        (a, b) =>
          (rank.get(a.o.label) ?? rank.size) - (rank.get(b.o.label) ?? rank.size) ||
          a.index - b.index,
      )
      .map(({ o }) => o);
  let shown = 0;
  const walk = (unordered: Placed[], depth: number, prefix: string) => {
    const list = ordered(unordered);
    list.forEach((o, index) => {
      const path = prefix ? `${prefix}-${index + 1}` : String(index + 1);
      paths.set(o.id, path);
      const fold = Boolean(options.folded) && !prefix && shown++ > 0;
      rows.push({
        kind: "label",
        depth,
        name: o.label,
        label: o.label,
        path,
        outside: !prefix && withParentLabel.has(o.label),
        folded: fold,
      });
      const children = objects.filter((c) => parents.get(c.id) === o.id);
      if (fold) {
        // Still numbered, so the tags over the image say the same.
        const number = (list: Placed[], at: string) =>
          list.forEach((c, k) => {
            paths.set(c.id, `${at}-${k + 1}`);
            number(
              objects.filter((x) => parents.get(x.id) === c.id),
              `${at}-${k + 1}`,
            );
          });
        number(children, path);
        return;
      }
      rows.push(...attributeRows(o, depth + 1));
      walk(children, depth + 1, path);
    });
  };
  walk(
    objects.filter((o) => !parents.get(o.id)),
    1,
    "",
  );
  return { rows, paths };
}
