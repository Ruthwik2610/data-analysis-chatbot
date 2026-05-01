import { fireEvent, render, screen } from "@testing-library/react";
import { ResultBlock } from "../ResultBlock";
import type { ResultPayload } from "@/lib/types";

const result: ResultPayload = {
  title: "Revenue by category",
  viz: "bar",
  elapsed_ms: 12,
  sql: "select category, revenue from sales",
  how: "Grouped revenue by category.",
  columns: ["category", "revenue"],
  rows: [["Classic", 206987], ["Veggie", 176577]],
  row_count: 2,
  truncated: false,
};

describe("ResultBlock", () => {
  it("lets users refine the displayed chart type", () => {
    render(<ResultBlock result={result} />);

    fireEvent.change(screen.getByLabelText("Chart type"), { target: { value: "pie" } });

    expect(screen.getByLabelText("Chart type")).toHaveValue("pie");
    expect(screen.getByTitle("Show table")).toBeInTheDocument();
    expect(screen.getByTitle("Copy SQL")).toBeInTheDocument();
  });
});
