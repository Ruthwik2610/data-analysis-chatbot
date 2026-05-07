import { render, screen, within } from "@testing-library/react";
import { MessageList } from "../MessageList";
import type { Message } from "@/lib/types";

beforeAll(() => {
  Element.prototype.scrollTo = vi.fn();
});

describe("MessageList markdown rendering", () => {
  it("formats insight-heavy assistant answers into sections, metric cards, tables, and callouts", () => {
    const messages: Message[] = [
      {
        id: "a1",
        role: "assistant",
        content: [
          "## Overall Business Summary",
          "- 21,350 orders | $817,860 total revenue | ~$16.82 avg order value | 2.3 pizzas/order",
          "---",
          "## Category Profitability (after cost)",
          "| Category | Revenue | Profit | Margin |",
          "|----------|---------|--------|--------|",
          "| Classic | $206,987 | $53,131 | 25.7% |",
          "| Veggie | $176,577 | $36,418 | 20.6% |",
          "> Classic wins on both revenue and profit.",
          "## Bottom Line Recommendations",
          "- Feature the Green Garden.",
          "- Run Sunday specials.",
        ].join("\n"),
      },
    ];

    render(
      <MessageList
        messages={messages}
        loading={false}
        onPendingChoice={vi.fn()}
        onPickFile={vi.fn()}
        onConnectClick={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "Overall Business Summary" })).toBeInTheDocument();
    expect(screen.getByText("$817,860 total revenue")).toBeInTheDocument();

    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Category" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "Classic" })).toBeInTheDocument();
    expect(screen.getByText("Classic wins on both revenue and profit.")).toBeInTheDocument();
    expect(screen.getByText("Feature the Green Garden.")).toBeInTheDocument();
  });

  it("keeps structured query result charts separate from assistant markdown formatting", () => {
    const messages: Message[] = [
      {
        id: "a1",
        role: "assistant",
        content: "Here is the revenue chart.",
        result: {
          title: "Revenue by category",
          viz: "bar",
          elapsed_ms: 12,
          sql: "select category, revenue from sales",
          how: "Grouped revenue by category.",
          columns: ["category", "revenue"],
          rows: [["Classic", 206987], ["Veggie", 176577]],
          row_count: 2,
          truncated: false,
        },
      },
    ];

    render(
      <MessageList
        messages={messages}
        loading={false}
        onPendingChoice={vi.fn()}
        onPickFile={vi.fn()}
        onConnectClick={vi.fn()}
      />,
    );

    expect(screen.getByText(/Revenue by category/)).toBeInTheDocument();
    expect(screen.getByTitle("Download CSV")).toBeInTheDocument();
    expect(screen.getByTitle("Show table")).toBeInTheDocument();
  });

  it("uses a responsive layout for empty-state action cards", () => {
    render(
      <MessageList
        messages={[]}
        loading={false}
        onPendingChoice={vi.fn()}
        onPickFile={vi.fn()}
        onConnectClick={vi.fn()}
      />,
    );

    expect(screen.getByTestId("empty-action-grid")).toHaveClass("flex-col", "sm:flex-row");
  });

  it("renders the premium Unipro empty-state hero", () => {
    render(
      <MessageList
        messages={[]}
        loading={false}
        onPendingChoice={vi.fn()}
        onPickFile={vi.fn()}
        onConnectClick={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: /Analyze your business data with AI/i })).toBeInTheDocument();
    expect(screen.getByText("Upload files, connect APIs, and generate intelligent insights instantly.")).toBeInTheDocument();
    expect(screen.getByText("Powered by advanced AI • Secure • Private")).toBeInTheDocument();
  });

  it("shows answer actions for assistant text and project saves", () => {
    render(
      <MessageList
        messages={[{ id: "a1", role: "assistant", content: "Revenue increased by 12%." }]}
        loading={false}
        onPendingChoice={vi.fn()}
        onPickFile={vi.fn()}
        onConnectClick={vi.fn()}
        currentProjectId="proj_1"
        onSaveProjectNote={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Copy answer" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save to project notes" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask follow-up" })).toBeInTheDocument();
  });
});
