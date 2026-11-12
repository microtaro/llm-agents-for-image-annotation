// The selected object of a master draft: its label (of the same shape), its parent (an object of
// the label's parent label) and its attributes, as the instruction defines them.
import type { LabelDefinition } from "@/api/types";
import { t } from "@/i18n";
import type { EditShape } from "@/lib/editing";

const FIELD = "rounded-md border border-line bg-surface px-2 py-1";

export function ObjectForm({
  shape,
  shapes,
  definitions,
  names,
  onChange,
}: {
  shape: EditShape;
  shapes: EditShape[];
  definitions: LabelDefinition[];
  names: Record<string, string>;
  onChange: (shape: EditShape) => void;
}) {
  const definition = definitions.find((d) => d.name === shape.label);
  const sameShape = definitions.filter(
    (d) => d.shape === shape.geometry.type || d.name === shape.label,
  );
  const parents = definition?.parent ? shapes.filter((s) => s.label === definition.parent) : [];
  const put = (change: Partial<EditShape>) => onChange({ ...shape, ...change, changed: true });

  return (
    <div className="flex flex-col gap-2 text-body">
      <label className="flex items-center gap-2">
        <span className="w-16 text-muted-foreground">{t("object.label")}</span>
        <select
          className={`${FIELD} flex-1`}
          value={shape.label}
          onChange={(e) => put({ label: e.target.value, parent: null, attributes: {} })}
        >
          {sameShape.map((d) => (
            <option key={d.name} value={d.name}>
              {d.name}
            </option>
          ))}
        </select>
      </label>
      {definition?.parent && (
        <label className="flex items-center gap-2">
          <span className="w-16 text-muted-foreground">{t("object.parent")}</span>
          <select
            className={`${FIELD} flex-1`}
            value={shape.parent ?? ""}
            onChange={(e) => put({ parent: e.target.value || null })}
          >
            <option value="">{t("label.parent.none")}</option>
            {parents.map((p) => (
              <option key={p.id} value={p.id}>
                {names[p.id] ?? p.label}
              </option>
            ))}
          </select>
        </label>
      )}
      {definition?.attributes.map((attribute) => {
        const value = shape.attributes[attribute.name];
        const set = (next: string) => {
          const attributes = { ...shape.attributes };
          if (next === "") delete attributes[attribute.name];
          else attributes[attribute.name] = attribute.type === "number" ? Number(next) : next;
          put({ attributes });
        };
        return (
          <label
            key={attribute.name}
            className="flex items-center gap-2"
            title={attribute.description}
          >
            <span className="w-16 truncate text-muted-foreground">{attribute.name}</span>
            {attribute.type === "choice" ? (
              <select
                className={`${FIELD} flex-1`}
                value={value === undefined ? "" : String(value)}
                onChange={(e) => set(e.target.value)}
              >
                <option value="">{t("object.value.none")}</option>
                {(attribute.choices ?? []).map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className={`${FIELD} min-w-0 flex-1`}
                type={attribute.type === "number" ? "number" : "text"}
                value={value === undefined ? "" : String(value)}
                onChange={(e) => set(e.target.value)}
              />
            )}
          </label>
        );
      })}
    </div>
  );
}
