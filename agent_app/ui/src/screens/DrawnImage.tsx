// An image with objects drawn over it (the decision views, types design 16.3.1; out of the box's
// screen).
import type { Annotation, GalleryItem } from "@/api/types";
import { thumbnailUrl } from "@/api/client";
import { Shapes } from "@/components/Shapes";

export type Image = GalleryItem["image"];

/** An image with objects drawn over it, as wide as given. */
export function Drawn({
  image,
  objects,
  colors,
  width,
}: {
  image: Pick<Image, "id" | "name" | "width" | "height">;
  objects: Annotation[];
  colors: Record<string, string>;
  width: number;
}) {
  const height = Math.round((width * image.height) / image.width);
  return (
    <span
      className="relative block max-w-full shrink"
      style={{ width, aspectRatio: `${width} / ${height}` }}
    >
      <img
        src={thumbnailUrl(image.id, width * 2)}
        alt={image.name}
        className="block h-full w-full object-contain"
      />
      <span className="absolute inset-0">
        <Shapes
          width={image.width}
          height={image.height}
          annotations={objects.filter((o) => o.geometry)}
          colors={colors}
          shownHeight={height}
        />
      </span>
    </span>
  );
}
