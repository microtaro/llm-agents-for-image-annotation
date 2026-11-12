import { describe as group, expect, it } from "vite-plus/test";
import type { GalleryItem } from "@/api/types";
import { cardLine, showGoing } from "../GalleryCard";

const item = (badge: GalleryItem["badge"]) =>
  ({ image: { id: "a", name: "a.png" }, badge, annotations: [] }) as unknown as GalleryItem;

group("card badge", () => {
  it("keeps a run's time and cost first on the line (found 2026-10-06)", () => {
    const line = cardLine(
      item({ kind: "detected", elapsed_ms: 40000, cost_usd: "0.32" }),
      "run",
      (model) => model ?? "",
    );
    expect(line.startsWith("40s · $0.320")).toBe(true);
  });
});

group("the run going on the card", () => {
  it("says it once (user 2026-10-15: annotating twice on one image)", () => {
    expect(showGoing("running", { waiting: true })).toBe(false);
    expect(showGoing("running", { waiting: false })).toBe(true);
    expect(showGoing(undefined, { waiting: false })).toBe(false);
  });
});
