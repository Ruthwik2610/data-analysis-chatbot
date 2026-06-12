import { fireEvent, render, screen } from "@testing-library/react";
import { ArtifactsPanel } from "../ArtifactsPanel";
import type { Message, Source } from "@/lib/types";

const messages: Message[] = [
  {
    id: "a1",
    role: "assistant",
    content: "Business analysis complete.",
    result: {
      title: "Primary result",
      viz: "bar",
      elapsed_ms: 10,
      sql: "select category, revenue from sales",
      how: "",
      columns: ["category", "revenue"],
      rows: [["Classic", 206987]],
      row_count: 1,
      truncated: false,
    },
    artifacts: [
      {
        title: "Revenue by category",
        viz: "bar",
        elapsed_ms: 10,
        sql: "select category, revenue from sales",
        how: "",
        columns: ["category", "revenue"],
        rows: [["Classic", 206987], ["Veggie", 176577]],
        row_count: 2,
        truncated: false,
      },
      {
        title: "Revenue by month",
        viz: "line",
        elapsed_ms: 12,
        sql: "select month, revenue from sales",
        how: "",
        columns: ["month", "revenue"],
        rows: [["2026-05-01", 817860], ["2026-06-01", 912000]],
        row_count: 2,
        truncated: false,
      },
    ],
  },
];

const sources: Source[] = [
  { id: "s1", name: "pizza_sales.csv", kind: "csv", rows: 48620, active: true },
  { id: "s2", name: "warehouse_mcp", kind: "mcp", rows: 6, active: false },
];

const sourcePreview = {
  name: "pizza_sales.csv",
  kind: "csv",
  rows: 48620,
  columns: ["category", "revenue"],
  preview_rows: [["Classic", 206987], ["Veggie", 176577]],
  schema: [{ name: "category", type: "TEXT" }, { name: "revenue", type: "INTEGER" }],
};

describe("ArtifactsPanel", () => {
  it("lists and selects multiple artifacts from one assistant message", () => {
    const onSelectArtifact = vi.fn();
    render(
      <ArtifactsPanel
        messages={messages}
        open
        selectedArtifactId="a1:artifact:0"
        onSelectArtifact={onSelectArtifact}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("2 artifacts")).toBeInTheDocument();
    expect(screen.getAllByText("Revenue by category").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /Revenue by month/i }));
    expect(onSelectArtifact).toHaveBeenCalledWith("a1:artifact:1");
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <ArtifactsPanel
        messages={messages}
        open={false}
        selectedArtifactId={null}
        onSelectArtifact={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("lists sources inside artifacts instead of the sidebar", () => {
    const onOpenSource = vi.fn();
    const onToggleSource = vi.fn();
    const onDeleteSource = vi.fn();
    render(
      <ArtifactsPanel
        messages={messages}
        sources={sources}
        selectedSourceIds={["s1"]}
        open
        selectedArtifactId="a1:artifact:0"
        selectedSourceId={null}
        sourcePreviewData={null}
        sourcePreviewLoading={false}
        onSelectArtifact={vi.fn()}
        onOpenSource={onOpenSource}
        onToggleSource={onToggleSource}
        onDeleteSource={onDeleteSource}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Sources")).toBeInTheDocument();
    expect(screen.getByText("pizza_sales")).toBeInTheDocument();
    expect(screen.getByText("48,620 rows")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Preview source pizza_sales" }));
    expect(onOpenSource).toHaveBeenCalledWith("s1");

    fireEvent.click(screen.getByRole("button", { name: "Toggle source pizza_sales" }));
    expect(onToggleSource).toHaveBeenCalledWith("s1");

    fireEvent.click(screen.getByRole("button", { name: "Delete source pizza_sales" }));
    expect(onDeleteSource).toHaveBeenCalledWith("s1");
  });

  it("renders source preview content in the artifacts panel", () => {
    render(
      <ArtifactsPanel
        messages={messages}
        sources={sources}
        selectedSourceIds={["s1"]}
        open
        selectedArtifactId="a1:artifact:0"
        selectedSourceId="s1"
        sourcePreviewData={sourcePreview}
        sourcePreviewLoading={false}
        onSelectArtifact={vi.fn()}
        onOpenSource={vi.fn()}
        onToggleSource={vi.fn()}
        onDeleteSource={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText("Source Preview")).toBeInTheDocument();
    expect(screen.getByText("pizza_sales.csv")).toBeInTheDocument();
    expect(screen.getAllByText("category").length).toBeGreaterThan(0);
    expect(screen.getByText("Classic")).toBeInTheDocument();
    expect(screen.getByText("206987")).toBeInTheDocument();
  });
});
