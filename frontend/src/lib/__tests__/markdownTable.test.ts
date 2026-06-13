import { describe, expect, it } from "vitest";

import { extractFirstMarkdownTable, tableCoversResult, tableToCsv } from "../markdownTable";

describe("markdownTable helpers", () => {
  it("extracts the first GitHub-flavored markdown table", () => {
    const text = [
      "Here are the rooms:",
      "",
      "| Room | Type | Rate |",
      "|---|---|---|",
      "| 207 | Deluxe | 6,350 |",
      "| 406 | Deluxe | 6,650 |",
    ].join("\n");

    expect(extractFirstMarkdownTable(text)).toEqual({
      columns: ["Room", "Type", "Rate"],
      rows: [["207", "Deluxe", "6,350"], ["406", "Deluxe", "6,650"]],
    });
  });

  it("detects when a markdown table covers the structured result columns", () => {
    expect(tableCoversResult(["Room Type", "Bed"], ["room_type", "bed", "rate"])).toBe(true);
    expect(tableCoversResult(["Metric", "Value"], ["room", "type", "bed", "rate", "view"])).toBe(false);
  });

  it("serializes markdown table data as escaped CSV", () => {
    expect(tableToCsv({
      columns: ["Name", "Note"],
      rows: [["Alice, A.", 'She said "hi"']],
    })).toBe('Name,Note\n"Alice, A.","She said ""hi"""');
  });
});
