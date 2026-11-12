// A reference as the worker AI sees it: the image with the objects it is an example of drawn
// (definition 38.1), its name and how many, on the plan's whole screen and in the plan book alike
// (user 2026-10-27: the book named the references without showing them).
import type { ReactNode } from "react";
import type { Reference } from "@/api/types";
import type { FigureImage } from "@/components/PlanFigure";
import { t } from "@/i18n";
import { Drawn } from "./DrawnImage";

export function ReferenceFigure({
  reference,
  image,
  colors,
  width,
  children,
}: {
  reference: Reference;
  image: FigureImage | undefined;
  colors: Record<string, string>;
  /** The drawn image's width. */
  width: number;
  /** What can be done with it, under its name. */
  children?: ReactNode;
}) {
  return (
    <figure
      className="relative m-0 flex flex-col gap-1 rounded-md border border-line bg-surface p-1.5"
      style={{ width: width + 12, maxWidth: "100%" }}
    >
      {image ? (
        <Drawn image={image} objects={reference.annotations} colors={colors} width={width} />
      ) : (
        <span className="text-muted-foreground">{reference.image_id}</span>
      )}
      <figcaption className="flex flex-col gap-0.5">
        <b className="truncate">{image?.name ?? reference.image_id}</b>
        <span className="text-muted-foreground">
          {t("common.objects", { count: reference.annotations.length })}
          {reference.note ? ` · ${reference.note}` : ""}
        </span>
        {children}
      </figcaption>
    </figure>
  );
}
