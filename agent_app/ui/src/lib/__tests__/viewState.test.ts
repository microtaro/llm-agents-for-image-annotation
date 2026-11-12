import { describe, expect, it } from "vite-plus/test";
import { talkPlaceOfBox } from "../viewState";

describe("where a box is answered", () => {
  it("is its worker's talk at the worker's place (definition 48.12: the reception's box of a dataset went to the dataset's talk, where the reception is not)", () => {
    expect(talkPlaceOfBox({ agent: "reception", dataset_id: "d1" })).toBe("library");
    expect(talkPlaceOfBox({ agent: "reception", dataset_id: null })).toBe("library");
    expect(talkPlaceOfBox({ agent: "steward", dataset_id: "d1" })).toBe("d1");
  });
});
