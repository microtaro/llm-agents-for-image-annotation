// The objects of one image as a table: a row per object, children under their parent, a column
// per attribute (the same rows as the gallery's table and the loupe's list, DESIGN.md). Used
// where a decision shows its data (types design 16.3.1).
import type { Annotation, GalleryItem } from "@/api/types";
import { LabelDot } from "@/components/LabelColors";
import { t } from "@/i18n";
import { attributeColumns, buildRows } from "@/lib/table";
import type { Image } from "./DrawnImage";

export function ObjectTable({
  image,
  objects,
  colors,
  pointed = null,
  onPoint,
}: {
  image: Image;
  objects: Annotation[];
  colors: Record<string, string>;
  /** The object pointed at (its row marked). */
  pointed?: string | null;
  onPoint?: (id: string | null) => void;
}) {
  const asItem = {
    image,
    annotations: objects,
    badge: { kind: "none" },
  } as unknown as GalleryItem;
  const rows = buildRows([asItem]);
  // One result's objects in a decision's data, by the values they hold.
  const names = attributeColumns([asItem], null);
  if (!rows.length)
    return <p className="m-0 text-muted-foreground">{t("decision.objects.none")}</p>;
  return (
    <div className="max-w-full overflow-x-auto">
      <table className="w-full border-collapse text-small whitespace-nowrap">
        <thead>
          <tr className="border-b border-line text-left text-muted-foreground">
            <th className="px-2 py-0.5 font-normal">{t("box.plan.object")}</th>
            <th className="px-2 py-0.5 font-normal">{t("table.parent")}</th>
            {names.map((name) => (
              <th key={name} className="px-2 py-0.5 font-normal">
                {name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.key}
              onMouseEnter={() => onPoint?.(row.annotationId)}
              onMouseLeave={() => onPoint?.(null)}
              className={`border-b border-line ${pointed === row.annotationId ? "bg-selected" : ""}`}
            >
              <td
                className="px-2 py-0.5 whitespace-nowrap"
                style={{ paddingLeft: `${0.5 + row.depth * 1.25}rem` }}
              >
                <LabelDot color={colors[row.label]} />
                {row.number ? `${row.label} ${row.number}` : row.label}
              </td>
              <td className="px-2 py-0.5 text-muted-foreground">{row.parent}</td>
              {names.map((name) => (
                <td key={name} className="px-2 py-0.5">
                  {row.values[name] ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
