import { fireEvent, render, screen } from "@testing-library/react";
import { ArtifactsPanel } from "../ArtifactsPanel";
import type { Message } from "@/lib/types";

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

describe("ArtifactsPanel", () => {
  it("lists and selects multiple graph artifacts from one assistant message", () => {
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

    expect(screen.getByText("2 graphs")).toBeInTheDocument();
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
});
