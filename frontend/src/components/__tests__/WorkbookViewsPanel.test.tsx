import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { WorkbookViewsPanel } from "../WorkbookViewsPanel";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: {
    listWorkbookViews: vi.fn().mockResolvedValue([
      { id: "view_1", name: "revenue_by_segment", sql: "SELECT * FROM orders", columns: ["segment", "revenue"], row_count: 2 },
    ]),
    createWorkbookView: vi.fn().mockResolvedValue({ id: "view_2", name: "top_orders", columns: ["order_id"], row_count: 1 }),
    mergeWorkbookView: vi.fn().mockResolvedValue({ id: "view_3", name: "orders_customers", columns: ["order_id"], row_count: 2 }),
    updateWorkbookView: vi.fn().mockResolvedValue({ id: "view_1", name: "revenue_by_segment", columns: ["segment"], row_count: 2 }),
    deleteWorkbookView: vi.fn().mockResolvedValue(undefined),
    deployWorkbookCloudflare: vi.fn().mockResolvedValue({ worker_url: "https://workbook.workers.dev/mcp" }),
  },
}));

describe("WorkbookViewsPanel", () => {
  it("creates, merges, modifies, deletes, and exposes workbook views", async () => {
    render(<WorkbookViewsPanel connectorId="mcp_workbook" connectorName="Operations workbook" />);

    expect(await screen.findByText("revenue_by_segment")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("View name"), { target: { value: "top_orders" } });
    fireEvent.change(screen.getByLabelText("View SQL"), { target: { value: "SELECT order_id FROM orders LIMIT 1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create view" }));
    await waitFor(() => expect(api.createWorkbookView).toHaveBeenCalledWith("mcp_workbook", {
      name: "top_orders",
      sql: "SELECT order_id FROM orders LIMIT 1",
    }));

    fireEvent.change(screen.getByLabelText("Merge view name"), { target: { value: "orders_customers" } });
    fireEvent.change(screen.getByLabelText("Left table"), { target: { value: "orders" } });
    fireEvent.change(screen.getByLabelText("Right table"), { target: { value: "customers" } });
    fireEvent.change(screen.getByLabelText("Left key"), { target: { value: "order_id" } });
    fireEvent.change(screen.getByLabelText("Right key"), { target: { value: "order_id" } });
    fireEvent.click(screen.getByRole("button", { name: "Merge tables" }));
    await waitFor(() => expect(api.mergeWorkbookView).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Expose through Cloudflare" }));
    await waitFor(() => expect(api.deployWorkbookCloudflare).toHaveBeenCalledWith("mcp_workbook", {
      public_base_url: "https://unipro.share.zrok.io",
    }));
  });
});
