import { describe, expect, it } from "vite-plus/test";
import type { GalleryItem } from "@/api/types";
import { markOf } from "../imageUse";

const item = (kind: string, excluded = false, said = {}): GalleryItem => ({
  image: { id: kind, name: kind, width: 1, height: 1, origin: "real", source_path: null, excluded },
  badge: { kind, ...said },
  annotations: [],
});

describe("the card's one mark (types design 17.1)", () => {
  it("tells run from used for training, and running", () => {
    expect(markOf(item("no_result"))).toBe("none");
    expect(markOf(item("failed"))).toBe("none");
    expect(markOf(item("running", false, { waiting: true }))).toBe("running");
    expect(markOf(item("detected", false, { succeeded: true }))).toBe("ran");
    expect(markOf(item("result"))).toBe("adopted");
    const ran = { ...item("excluded", true), badge: { kind: "excluded", ran: true } };
    expect(markOf(ran)).toBe("ran");
    expect(markOf(item("excluded", true))).toBe("none");
  });
});
