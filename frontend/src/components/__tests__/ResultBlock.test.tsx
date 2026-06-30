import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import { ResultBlock } from "../ResultBlock";
import type { ResultPayload } from "@/lib/types";

const pdfMocks = vi.hoisted(() => ({
  lastDoc: null as any,
}));

vi.mock("jspdf", () => ({
  default: vi.fn().mockImplementation(function () {
    const doc = {
      internal: {
        pageSize: {
          getWidth: vi.fn(() => 595),
          getHeight: vi.fn(() => 842),
        },
      },
      setFont: vi.fn(),
      setFontSize: vi.fn(),
      setTextColor: vi.fn(),
      splitTextToSize: vi.fn((text: string) => [text]),
      text: vi.fn(),
      addPage: vi.fn(),
      addImage: vi.fn(),
      getImageProperties: vi.fn(() => ({ width: 1000, height: 500 })),
      save: vi.fn(),
    };
    pdfMocks.lastDoc = doc;
    return doc;
  }),
}));

vi.mock("jspdf-autotable", () => ({
  default: vi.fn(),
}));

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
  beforeEach(() => {
    vi.clearAllMocks();
    pdfMocks.lastDoc = null;
  });

  it("lets users refine the displayed chart type", () => {
    render(<ResultBlock result={result} />);

    fireEvent.change(screen.getByLabelText("Chart type"), { target: { value: "pie" } });

    expect(screen.getByLabelText("Chart type")).toHaveValue("pie");
    expect(screen.getByTitle("Show table")).toBeInTheDocument();
    expect(screen.getByTitle("Export result")).toBeInTheDocument();
    expect(screen.queryByTitle("Copy SQL")).not.toBeInTheDocument();
    expect(screen.queryByText("How I answered")).not.toBeInTheDocument();
    expect(screen.queryByText("select category, revenue from sales")).not.toBeInTheDocument();
    expect(screen.queryByText("Grouped revenue by category.")).not.toBeInTheDocument();
  });

  it("groups result exports in one dropdown", () => {
    render(<ResultBlock result={result} />);

    fireEvent.click(screen.getByTitle("Export result"));

    expect(screen.getByRole("menuitem", { name: "CSV" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "XLSX" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "PDF" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "JPEG" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Chart type"), { target: { value: "table" } });

    expect(screen.getByRole("menuitem", { name: "PDF" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "JPEG" })).not.toBeInTheDocument();
  });

  it("exports table PDFs without internal source metadata in the narrative", async () => {
    render(
      <ResultBlock
        result={result}
        narrative={[
          "Source: API direct.",
          "Model: openrouter/deepseek/deepseek-v4-flash.",
          "Revenue increased by category.",
        ].join("\n")}
      />,
    );

    fireEvent.change(screen.getByLabelText("Chart type"), { target: { value: "table" } });
    fireEvent.click(screen.getByTitle("Export result"));
    fireEvent.click(screen.getByRole("menuitem", { name: "PDF" }));

    await waitFor(() => expect(autoTable).toHaveBeenCalled());
    expect(jsPDF).toHaveBeenCalled();
    expect(pdfMocks.lastDoc.save).toHaveBeenCalledWith("revenue_by_category.pdf");

    const pdfText = pdfMocks.lastDoc.text.mock.calls
      .map(([text]: [string | string[]]) => Array.isArray(text) ? text.join(" ") : text)
      .join("\n");
    expect(pdfText).toContain("Revenue increased by category.");
    expect(pdfText).not.toContain("Source: API direct.");
    expect(pdfText).not.toContain("Model: openrouter/deepseek/deepseek-v4-flash.");
  });

  it("renders single-value answers inline without result-card exports", () => {
    render(
      <ResultBlock
        result={{
          title: "Count",
          viz: "card",
          elapsed_ms: 4,
          sql: "select count(*) from orders",
          how: "",
          columns: ["count"],
          rows: [[48620]],
          row_count: 1,
          truncated: false,
        }}
      />,
    );

    expect(screen.getByText("Count")).toBeInTheDocument();
    expect(screen.getByText("48,620")).toBeInTheDocument();
    expect(screen.queryByTitle("Export result")).not.toBeInTheDocument();
    expect(screen.queryByText(/1 rows/i)).not.toBeInTheDocument();
  });

  it("renders wide single-row lookup results as a table even when the payload says bar", () => {
    render(
      <ResultBlock
        result={{
          title: "Multi-source Result",
          viz: "bar",
          elapsed_ms: 42,
          sql: "select * from business_data where voucherseries = 'PR'",
          how: "Display: bar.",
          columns: ["voucherlineno", "voucherseries", "voucherno", "date", "branch", "account"],
          rows: [[1, "PR", 10, "2026-06-29", "Hyderabad", "Cash"]],
          row_count: 1,
          truncated: false,
        }}
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Voucherlineno" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "PR" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Bar chart")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Chart type")).not.toBeInTheDocument();
  });

  it("renders very wide one-row lookup results without chart controls", () => {
    const columns = Array.from({ length: 182 }, (_, index) => `field_${index + 1}`);
    const rows = [columns.map((column, index) => index === 1 ? "PR" : `${column}_value`)];

    render(
      <ResultBlock
        result={{
          title: "Multi-source Result",
          viz: "table",
          elapsed_ms: 52,
          sql: "select * from business_data where voucherseries = 'PR'",
          how: "Display: table.",
          columns,
          rows,
          row_count: 1,
          truncated: false,
          view_type: "table",
        }}
      />,
    );

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Field 1" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "PR" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Chart type")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Bar chart")).not.toBeInTheDocument();
  });

  it("renders explicit bar and pie chart selections without falling back to a line chart", () => {
    render(
      <ResultBlock
        result={{
          ...result,
          title: "Revenue by month",
          viz: "bar",
          columns: ["month", "revenue"],
          rows: [["2026-05-01", 817860], ["2026-06-01", 912000]],
        }}
      />,
    );

    expect(screen.getByLabelText("Bar chart")).toBeInTheDocument();
    expect(screen.queryByLabelText("Line chart")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Chart type"), { target: { value: "pie" } });

    expect(screen.getByLabelText("Pie chart")).toBeInTheDocument();
    expect(screen.queryByLabelText("Line chart")).not.toBeInTheDocument();
  });
});
