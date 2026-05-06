import { describe, expect, it } from "vitest";
import { formatArchiveSkippedNote } from "../uploadMessages";

describe("formatArchiveSkippedNote", () => {
  it("returns an empty note when every archive PDF attached", () => {
    expect(formatArchiveSkippedNote()).toBe("");
  });

  it("lists skipped archive PDFs and their reasons", () => {
    expect(formatArchiveSkippedNote([
      { file_name: "scan.pdf", error: "No tables found" },
      { file_name: "huge.pdf", error: "Too large" },
    ])).toBe(" 2 PDFs were skipped: scan: No tables found; huge: Too large.");
  });

  it("caps long skipped lists", () => {
    expect(formatArchiveSkippedNote([
      { file_name: "one.pdf", error: "No tables found" },
      { file_name: "two.pdf", error: "No tables found" },
      { file_name: "three.pdf", error: "No tables found" },
      { file_name: "four.pdf", error: "No tables found" },
    ])).toContain("1 more");
  });
});
