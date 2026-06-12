import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ResultBlock } from "../ResultBlock";
import type { ResultPayload } from "@/lib/types";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

const pdfMocks = vi.hoisted(() => ({
  lastDoc: null as any,
}));

vi.mock("jspdf", () => {
  return {
    default: vi.fn().mockImplementation(function () {
      pdfMocks.lastDoc = {
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
      return pdfMocks.lastDoc;
    }),
  };
});

vi.mock("jspdf-autotable", () => {
  return {
    default: vi.fn(),
  };
});

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

    fireEvent.change(screen.getByLabelText("Visualization"), { target: { value: "pie" } });

    expect(screen.getByLabelText("Visualization")).toHaveValue("pie");
    fireEvent.click(screen.getByRole("button", { name: "Export result" }));
    expect(screen.getByRole("button", { name: "Export result as CSV" })).toBeInTheDocument();
    expect(screen.queryByTitle("Copy SQL")).not.toBeInTheDocument();
    expect(screen.queryByText("How I answered")).not.toBeInTheDocument();
    expect(screen.queryByText("select category, revenue from sales")).not.toBeInTheDocument();
  });

  it("exports table rows instead of an image when the visible PDF view is table", async () => {
    const imageBackedResult: ResultPayload = {
      ...result,
      viz: "chart",
      image_b64: "old-chart-image",
    };

    render(<ResultBlock result={imageBackedResult} />);

    fireEvent.change(screen.getByLabelText("Visualization"), { target: { value: "table" } });
    fireEvent.click(screen.getByRole("button", { name: "Export result" }));
    fireEvent.click(screen.getByRole("button", { name: "Export result as PDF" }));

    await waitFor(() => expect(autoTable).toHaveBeenCalled());
    const doc = pdfMocks.lastDoc;
    expect(doc.addImage).not.toHaveBeenCalled();
    expect(autoTable).toHaveBeenCalledWith(
      doc,
      expect.objectContaining({
        head: [["Category", "Revenue"]],
        body: [["Classic", "206,987"], ["Veggie", "176,577"]],
      }),
    );
  });
});
