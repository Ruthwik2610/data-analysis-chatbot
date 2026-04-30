import { fireEvent, render, screen } from "@testing-library/react";
import { ConnectorPopover } from "../ConnectorPopover";

vi.mock("@/lib/api", () => ({
  api: {
    listConnectors: vi.fn().mockResolvedValue([]),
    listMCPConnectors: vi.fn().mockResolvedValue([]),
    addMCPConnector: vi.fn().mockResolvedValue({
      id: "mcp_1",
      name: "Warehouse",
      url: "https://example.com/mcp",
      status: "connected",
      tools: [],
      scope: "project",
      project_ids: ["proj_1"],
    }),
  },
}));

describe("ConnectorPopover", () => {
  it("renders source modes as accessible segmented tabs", async () => {
    const anchorRef = { current: document.createElement("button") };

    render(
      <ConnectorPopover
        open
        onClose={vi.fn()}
        onAttached={vi.fn()}
        anchorRef={anchorRef}
      />,
    );

    expect(screen.getByRole("tab", { name: "API" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "MCP" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: "Excel" })).toHaveAttribute("aria-selected", "false");

    fireEvent.click(screen.getByRole("tab", { name: "Excel" }));

    expect(screen.getByRole("tab", { name: "Excel" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByPlaceholderText("Local path to .xlsx file")).toBeInTheDocument();
  });

  it("defaults MCP connectors to the active project scope", async () => {
    const anchorRef = { current: document.createElement("button") };

    render(
      <ConnectorPopover
        open
        onClose={vi.fn()}
        onAttached={vi.fn()}
        anchorRef={anchorRef}
        currentProjectId="proj_1"
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: "MCP" }));
    fireEvent.change(screen.getByPlaceholderText("Server name (optional, e.g. BigQuery)"), {
      target: { value: "Warehouse" },
    });
    fireEvent.change(screen.getByPlaceholderText("Bridge URL (https://example.com/mcp)"), {
      target: { value: "https://example.com/mcp" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    const { api } = await import("@/lib/api");
    expect(api.addMCPConnector).toHaveBeenCalledWith("https://example.com/mcp", "Warehouse", {
      scope: "project",
      project_id: "proj_1",
    });
  });
});
