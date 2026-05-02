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
      files: [{ id: "file_1", project_id: "proj_1", file_path: null, source_id: "src_pizza", source_name: "pizza_sales.csv", sheet_name: null, created_at: 1 }],
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
    listProjectNotes: vi.fn().mockResolvedValue([
      {
        id: "note_1",
        project_id: "proj_1",
        title: "Revenue finding",
        content: "Revenue increased by 12%.",
        source_message_id: "msg_1",
        created_at: 1,
      },
    ]),
    getProjectInstructions: vi.fn().mockResolvedValue({
      project_id: "proj_1",
      instructions: { category: "sales", notes: "Orders are distinct order_id." },
    }),
    updateProjectInstructions: vi.fn().mockResolvedValue({
      project_id: "proj_1",
      instructions: { category: "sales", notes: "Orders are distinct order_id." },
    }),
    rebuildProjectProfile: vi.fn().mockResolvedValue({
      project_id: "proj_1",
      instructions: { category: "sales", notes: "Orders are distinct order_id." },
    }),
    getSourceInstructions: vi.fn().mockResolvedValue({
      source_id: "src_pizza",
      instructions: { row_grain: "line_item", notes: "Quantity means pizzas sold." },
    }),
    updateSourceInstructions: vi.fn().mockResolvedValue({
      source_id: "src_pizza",
      instructions: { row_grain: "line_item", notes: "Quantity means pizzas sold." },
    }),
    deleteProjectNote: vi.fn().mockResolvedValue(undefined),
    bindProjectMCP: vi.fn().mockResolvedValue({ ok: true }),
    unbindProjectMCP: vi.fn().mockResolvedValue(undefined),
    updateProject: vi.fn().mockResolvedValue({
      id: "proj_1",
      title: "Restaurant sandbox",
      created_at: 1,
      updated_at: 3,
      files: [],
    }),
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

  it("renames the project from the dialog", async () => {
    const onUpdate = vi.fn();
    render(<ProjectDialog projectId="proj_1" onClose={vi.fn()} onUpdate={onUpdate} />);

    const titleInput = await screen.findByLabelText("Project name");
    fireEvent.change(titleInput, { target: { value: "Restaurant sandbox" } });
    fireEvent.click(screen.getByRole("button", { name: "Save project name" }));

    await waitFor(() => {
      expect(api.updateProject).toHaveBeenCalledWith("proj_1", { title: "Restaurant sandbox" });
      expect(onUpdate).toHaveBeenCalled();
    });
  });

  it("renders saved project notes", async () => {
    render(<ProjectDialog projectId="proj_1" onClose={vi.fn()} onUpdate={vi.fn()} />);

    expect(await screen.findByText("Revenue finding")).toBeInTheDocument();
    expect(screen.getByText("Revenue increased by 12%.")).toBeInTheDocument();
  });

  it("saves project and file instructions", async () => {
    render(<ProjectDialog projectId="proj_1" onClose={vi.fn()} onUpdate={vi.fn()} />);

    const projectRules = await screen.findByLabelText("Project rules");
    expect(projectRules).toHaveValue("Orders are distinct order_id.");
    fireEvent.change(projectRules, { target: { value: "Revenue means total_price." } });
    fireEvent.click(screen.getByRole("button", { name: "Save rules" }));

    await waitFor(() => {
      expect(api.updateProjectInstructions).toHaveBeenCalledWith("proj_1", {
        category: "sales",
        notes: "Revenue means total_price.",
      });
    });

    fireEvent.change(screen.getByLabelText("Instruction source"), { target: { value: "src_pizza" } });
    expect(await screen.findByLabelText("File rules")).toHaveValue("Quantity means pizzas sold.");
    fireEvent.change(screen.getByLabelText("File rules"), { target: { value: "Orders are distinct order_id." } });
    fireEvent.click(screen.getByRole("button", { name: "Save file rules" }));

    await waitFor(() => {
      expect(api.updateSourceInstructions).toHaveBeenCalledWith("src_pizza", expect.objectContaining({
        row_grain: "line_item",
        notes: "Orders are distinct order_id.",
      }));
    });
  });
});
