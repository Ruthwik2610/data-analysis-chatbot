import { describe, expect, it } from "vitest";
import { formatArchiveSkippedNote, formatWorkbookMCPConnectedMessage } from "../uploadMessages";

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

describe("formatWorkbookMCPConnectedMessage", () => {
  it("shows the generated MCP URL when workbook exposure succeeds", () => {
    expect(formatWorkbookMCPConnectedMessage(
      [{ id: "src_orders", name: "operations.xlsx - Orders", kind: "xlsx", rows: 2, active: false }],
      {
        id: "mcp_workbook",
        name: "operations.xlsx workbook",
        url: null,
        status: "connected",
        tools: [],
        cloudflare: {
          connector_id: "mcp_workbook",
          worker_name: "unipro-workbook",
          worker_url: "https://unipro-workbook.workers.dev/mcp",
          created_at: 1,
          updated_at: 1,
        },
      },
    )).toContain("MCP URL: https://unipro-workbook.workers.dev/mcp");
  });

  it("does not expose raw MCP deployment errors", () => {
    const message = formatWorkbookMCPConnectedMessage(
      [{ id: "src_orders", name: "operations.xlsx - Orders", kind: "xlsx", rows: 2, active: false }],
      {
        id: "mcp_workbook",
        name: "operations.xlsx workbook",
        url: null,
        status: "connected",
        tools: [],
      },
      "Traceback: SELECT * FROM secrets WHERE api_key = 'abc'",
    );

    expect(message).toContain("public MCP URL could not be created");
    expect(message).not.toMatch(/select|api_key|traceback/i);
  });
});
