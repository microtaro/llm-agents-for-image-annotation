import { describe, expect, it } from "vite-plus/test";
import { sentencesOf } from "../draftText";

describe("the text cut into sentences, as the server does", () => {
  it("keeps each line, cut after 。 . ! ?", () => {
    expect(sentencesOf("箱を囲む。印字欄も囲む。\nLabels. Read them!")).toEqual([
      ["箱を囲む。", "印字欄も囲む。"],
      ["Labels.", " Read them!"],
    ]);
  });
});
