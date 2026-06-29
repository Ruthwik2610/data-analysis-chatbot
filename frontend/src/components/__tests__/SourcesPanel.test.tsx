import { fireEvent, render, screen } from "@testing-library/react";
import { SourcesPanel } from "../SourcesPanel";
import type { Connector, MCPConnector, Source } from "@/lib/types";

const sources: Source[] = [
  { id: "s1", name: "pizza_sales.csv", kind: "csv", rows: 48620, active: true },
  { id: "s2", name: "orders.csv", kind: "csv", rows: 9994, active: false },
];

const sourcePreview = {
  name: "pizza_sales.csv",
  kind: "csv",
  rows: 48620,
  columns: ["category", "revenue"],
  preview_rows: [["Classic", 206987], ["Veggie", 176577]],
  schema: [{ name: "category", type: "TEXT" }, { name: "revenue", type: "INTEGER" }],
};

const mcpConnectors: MCPConnector[] = [
  {
    id: "RapidAI_Database",
    name: "RapidAI_Database",
    url: null,
    status: "connected",
    tools: Array.from({ length: 88 }, (_, index) => ({ name: `tool_${index}` })),
  },
  {
    id: "SAP_EH8",
    name: "SAP_EH8",
    url: null,
    status: "error",
    tools: [],
  },
];

const apiConnectors: Connector[] = [
  {
    id: "conn_api_customers",
    kind: "api",
    label: "https://api.example.com/customers",
    config: {},
  },
];

describe("SourcesPanel", () => {
  it("lists source controls separately from artifacts", () => {
    const onOpenSource = vi.fn();
    const onToggleSource = vi.fn();
    const onDeleteSource = vi.fn();
    render(
      <SourcesPanel
        open
        sources={sources}
        selectedSourceIds={["s1"]}
        selectedSourceId={null}
        sourcePreviewData={null}
        sourcePreviewLoading={false}
        onOpenSource={onOpenSource}
        onToggleSource={onToggleSource}
        onDeleteSource={onDeleteSource}
        onCloseSourcePreview={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Sources")).toBeInTheDocument();
    expect(screen.getByText("pizza_sales")).toBeInTheDocument();
    expect(screen.getByText("48,620 rows")).toBeInTheDocument();
    expect(screen.getByLabelText("Source selected pizza_sales")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Preview source pizza_sales" }));
    expect(onOpenSource).toHaveBeenCalledWith("s1");

    fireEvent.click(screen.getByRole("button", { name: "Preview source orders" }));
    expect(onOpenSource).not.toHaveBeenCalledWith("s2");

    fireEvent.click(screen.getByRole("button", { name: "Toggle source pizza_sales" }));
    expect(onToggleSource).toHaveBeenCalledWith("s1");

    fireEvent.click(screen.getByRole("button", { name: "Delete source pizza_sales" }));
    expect(onDeleteSource).toHaveBeenCalledWith("s1");
  });

  it("renders and closes source preview content", () => {
    const onCloseSourcePreview = vi.fn();
    render(
      <SourcesPanel
        open
        sources={sources}
        selectedSourceIds={["s1"]}
        selectedSourceId="s1"
        sourcePreviewData={sourcePreview}
        sourcePreviewLoading={false}
        onOpenSource={vi.fn()}
        onToggleSource={vi.fn()}
        onDeleteSource={vi.fn()}
        onCloseSourcePreview={onCloseSourcePreview}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Source Preview")).toBeInTheDocument();
    expect(screen.getByText("pizza_sales.csv")).toBeInTheDocument();
    expect(screen.getAllByText("category").length).toBeGreaterThan(0);
    expect(screen.getByText("Classic")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close source preview" }));
    expect(onCloseSourcePreview).toHaveBeenCalledTimes(1);
  });

  it("shows selectable MCP bridge sources and status for unavailable bridges", () => {
    const onOpenSource = vi.fn();
    const onToggleSource = vi.fn();
    const onDeleteSource = vi.fn();
    const onRetryMCPConnector = vi.fn();
    render(
      <SourcesPanel
        open
        sources={[{ id: "mcp:RapidAI_Database", name: "RapidAI_Database", kind: "mcp", rows: 88, active: false }]}
        selectedSourceIds={["mcp:RapidAI_Database"]}
        selectedSourceId={null}
        sourcePreviewData={null}
        sourcePreviewLoading={false}
        mcpConnectors={mcpConnectors}
        onOpenSource={onOpenSource}
        onToggleSource={onToggleSource}
        onDeleteSource={onDeleteSource}
        onRetryMCPConnector={onRetryMCPConnector}
        onCloseSourcePreview={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("MCP bridges")).toBeInTheDocument();
    expect(screen.getByText("RapidAI_Database")).toBeInTheDocument();
    expect(screen.getByText("88 tools")).toBeInTheDocument();
    expect(screen.getByText("SAP_EH8")).toBeInTheDocument();
    expect(screen.getByText("Needs reconnect")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry MCP bridge SAP_EH8" }));
    expect(onRetryMCPConnector).toHaveBeenCalledWith("SAP_EH8");
    fireEvent.click(screen.getByRole("button", { name: "Toggle source RapidAI_Database" }));
    expect(onToggleSource).toHaveBeenCalledWith("mcp:RapidAI_Database");
    fireEvent.click(screen.getByRole("button", { name: "Preview source RapidAI_Database" }));
    expect(onOpenSource).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Delete source RapidAI_Database" }));
    expect(onDeleteSource).toHaveBeenCalledWith("mcp:RapidAI_Database");
  });

  it("shows API sources and saved APIs in the source panel", () => {
    const onToggleSource = vi.fn();
    const onUseConnector = vi.fn();
    const onDeleteConnector = vi.fn();
    render(
      <SourcesPanel
        open
        sources={[{ id: "src_api_orders", name: "https://api.example.com/orders", kind: "api", rows: 42, active: false }]}
        selectedSourceIds={[]}
        selectedSourceId={null}
        sourcePreviewData={null}
        sourcePreviewLoading={false}
        apiConnectors={apiConnectors}
        onOpenSource={vi.fn()}
        onToggleSource={onToggleSource}
        onDeleteSource={vi.fn()}
        onUseConnector={onUseConnector}
        onDeleteConnector={onDeleteConnector}
        onCloseSourcePreview={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("API sources")).toBeInTheDocument();
    expect(screen.getByText("orders")).toBeInTheDocument();
    expect(screen.getByText("Saved API")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Toggle source orders" }));
    expect(onToggleSource).toHaveBeenCalledWith("src_api_orders");

    fireEvent.click(screen.getByRole("button", { name: "Use API source https://api.example.com/customers" }));
    expect(onUseConnector).toHaveBeenCalledWith("conn_api_customers");

    fireEvent.click(screen.getByRole("button", { name: "Delete saved API source https://api.example.com/customers" }));
    expect(onDeleteConnector).toHaveBeenCalledWith("conn_api_customers");
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <SourcesPanel
        open={false}
        sources={sources}
        selectedSourceIds={["s1"]}
        selectedSourceId={null}
        sourcePreviewData={null}
        sourcePreviewLoading={false}
        onOpenSource={vi.fn()}
        onToggleSource={vi.fn()}
        onDeleteSource={vi.fn()}
        onCloseSourcePreview={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
