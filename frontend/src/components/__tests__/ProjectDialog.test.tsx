import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ProjectDialog } from "../ProjectDialog";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: {
    getProject: vi.fn().mockResolvedValue({
      id: "proj_1",
      title: "Restaurant ops",
      created_at: 1,
      updated_at: 2,
      files: [],
    }),
    listSources: vi.fn().mockResolvedValue([]),
    listMCPConnectors: vi.fn().mockResolvedValue([
      {
        id: "mcp_mysql",
        name: "MySQL",
        url: null,
        status: "connected",
        tools: [{ name: "query", description: "Run SQL" }],
        scope: "project",
        project_ids: ["proj_1"],
        description: "MySQL exposes 1 tool: query.",
      },
      {
        id: "mcp_bigquery",
        name: "BigQuery",
        url: null,
        status: "connected",
        tools: [{ name: "list_tables" }],
        scope: "project",
        project_ids: [],
        description: "BigQuery exposes 1 tool: list_tables.",
      },
    ]),
    bindProjectMCP: vi.fn().mockResolvedValue({ ok: true }),
    unbindProjectMCP: vi.fn().mockResolvedValue(undefined),
    addProjectFile: vi.fn(),
    removeProjectFile: vi.fn(),
  },
}));

describe("ProjectDialog", () => {
  it("renders linked MCP connectors and can bind another connector", async () => {
    render(<ProjectDialog projectId="proj_1" onClose={vi.fn()} onUpdate={vi.fn()} />);

    expect(await screen.findByText("MySQL")).toBeInTheDocument();
    expect(screen.getByText("MySQL exposes 1 tool: query.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Add database context"), { target: { value: "mcp_bigquery" } });
    fireEvent.click(screen.getByRole("button", { name: "Add database" }));

    await waitFor(() => {
      expect(api.bindProjectMCP).toHaveBeenCalledWith("proj_1", "mcp_bigquery");
    });
  });
});
