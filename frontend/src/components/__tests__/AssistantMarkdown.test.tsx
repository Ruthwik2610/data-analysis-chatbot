import { render, screen, within } from "@testing-library/react";
import { AssistantMarkdown } from "../AssistantMarkdown";

const insightAnswer = [
  "## Overall Business Summary",
  "- 21,350 orders | $817,860 total revenue | ~$16.82 avg order value | 2.3 pizzas/order",
  "",
  "## Category Profitability",
  "| Category | Revenue | Profit | Margin |",
  "|----------|---------|--------|--------|",
  "| Classic | $206,987 | $53,131 | 25.7% |",
  "| Veggie | $176,577 | $36,418 | 20.6% |",
  "> Classic wins on both revenue and profit.",
].join("\n");

describe("AssistantMarkdown", () => {
  it("renders headings as chat-native sections without card wrappers", () => {
    const { container } = render(<AssistantMarkdown content={insightAnswer} streaming={false} />);

    expect(screen.getByRole("heading", { name: "Overall Business Summary" })).toBeInTheDocument();
    expect(container.querySelector(".insight-section")).not.toBeInTheDocument();
  });

  it("renders metric rows as compact metric items", () => {
    render(<AssistantMarkdown content={insightAnswer} streaming={false} />);

    const metrics = screen.getAllByTestId("assistant-metric");
    expect(metrics).toHaveLength(4);
    expect(screen.getByText("$817,860 total revenue")).toBeInTheDocument();
  });

  it("renders markdown tables with accessible headers and cells", () => {
    render(<AssistantMarkdown content={insightAnswer} streaming={false} />);

    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Category" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "Classic" })).toBeInTheDocument();
  });

  it("renders blockquotes as callouts", () => {
    render(<AssistantMarkdown content={insightAnswer} streaming={false} />);

    expect(screen.getByTestId("assistant-callout")).toHaveTextContent("Classic wins");
  });

  it("renders asterisk and underscore emphasis as italic text", () => {
    const { container } = render(
      <AssistantMarkdown
        content={"*All four categories are close.*\n\n_Classic is slightly ahead._"}
        streaming={false}
      />,
    );

    const emphasized = Array.from(container.querySelectorAll("em")).map((node) => node.textContent);
    expect(emphasized).toEqual(["All four categories are close.", "Classic is slightly ahead."]);
  });

  it("uses lightweight rendering while streaming", () => {
    const { container } = render(<AssistantMarkdown content={insightAnswer} streaming />);

    expect(screen.getByText(/Overall Business Summary/)).toBeInTheDocument();
    expect(container.querySelector("table")).not.toBeInTheDocument();
  });
});
