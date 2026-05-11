import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import TestingPage from "./page";
import { api } from "@/lib/api";

vi.mock("@/components/admin/TestInputPane", () => ({
  default: () => <div>Test input pane</div>,
}));

vi.mock("@/components/admin/GradingInterface", () => ({
  default: () => <div>Grading interface</div>,
}));

vi.mock("@/components/admin/TestingDashboard", () => ({
  default: () => <div>Testing dashboard</div>,
}));

vi.mock("@/lib/api", () => ({
  api: {
    listTestSuites: vi.fn(),
    listTestRuns: vi.fn(),
    createAutoTestSuite: vi.fn(),
    listSources: vi.fn(),
    uploadFile: vi.fn(),
    resolvePending: vi.fn(),
  },
}));

describe("TestingPage auto suite generation", () => {
  beforeEach(() => {
    (api.listTestSuites as any).mockResolvedValue([]);
    (api.listTestRuns as any).mockResolvedValue([]);
    (api.createAutoTestSuite as any).mockResolvedValue({
      id: "suite_auto",
      name: "Auto suite",
      query_count: 4,
    });
    (api.listSources as any).mockResolvedValue([
      { id: "src_orders", name: "orders.csv", kind: "csv", rows: 120, active: true },
      { id: "src_customers", name: "customers.xlsx", kind: "xlsx", rows: 80, active: false },
    ]);
    vi.clearAllMocks();
  });

  it("asks which existing uploaded sources to use before auto-generating tests", async () => {
    render(<TestingPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Auto-create Tests/i }));

    expect(await screen.findByText("Choose sources to test")).toBeInTheDocument();
    expect(await screen.findByLabelText("orders.csv")).toBeInTheDocument();
    expect(screen.getByLabelText("customers.xlsx")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("orders.csv"));
    fireEvent.click(screen.getByRole("button", { name: /Generate from selected sources/i }));

    await waitFor(() => {
      expect(api.createAutoTestSuite).toHaveBeenCalledWith({ source_ids: ["src_orders"] });
    });
  });

  it("lets admins upload a new source when no existing source is available", async () => {
    (api.listSources as any).mockResolvedValue([]);
    render(<TestingPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Auto-create Tests/i }));

    expect(await screen.findByText("No uploaded sources yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Upload a source/i })).toBeInTheDocument();
  });
});
