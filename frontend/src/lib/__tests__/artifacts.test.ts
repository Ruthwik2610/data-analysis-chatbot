import { artifactItems } from "../artifacts";
import type { Message, ResultPayload } from "../types";

const chart = (title: string, viz: ResultPayload["viz"] = "bar"): ResultPayload => ({
  title,
  viz,
  elapsed_ms: 10,
  sql: "select label, value from facts",
  how: "",
  columns: ["label", "value"],
  rows: [["A", 10]],
  row_count: 1,
  truncated: false,
});

describe("artifactItems", () => {
  it("does not create artifacts for a single chart answer", () => {
    const messages: Message[] = [
      { id: "a1", role: "assistant", content: "One chart.", result: chart("Revenue by category") },
    ];

    expect(artifactItems(messages)).toEqual([]);
  });

  it("creates artifacts only when one answer has multiple graph results", () => {
    const messages: Message[] = [
      {
        id: "a1",
        role: "assistant",
        content: "Two charts.",
        result: chart("Revenue by category"),
        artifacts: [chart("Revenue by category"), chart("Revenue by month", "line")],
      },
    ];

    expect(artifactItems(messages).map((item) => item.result.title)).toEqual([
      "Revenue by category",
      "Revenue by month",
    ]);
  });

  it("keeps tables out of visual artifacts", () => {
    const messages: Message[] = [
      {
        id: "a1",
        role: "assistant",
        content: "A chart and a table.",
        artifacts: [chart("Revenue by category"), chart("Revenue detail", "table")],
      },
    ];

    expect(artifactItems(messages)).toEqual([]);
  });
});
