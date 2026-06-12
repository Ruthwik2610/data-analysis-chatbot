import { fireEvent, render, screen } from "@testing-library/react";
import { SourcesPanel } from "../SourcesPanel";
import type { Source } from "@/lib/types";

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
