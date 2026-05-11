import { render, screen, waitFor } from "@testing-library/react";
import { QueryLoopMetricsDashboard } from "../admin/QueryLoopMetricsDashboard";
import { api } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  api: {
    getQueryLoops: vi.fn().mockResolvedValue({
      summary: {
        total_queries: 2,
        high_loop_queries: 1,
        avg_tool_calls: 3.5,
        avg_rounds: 2,
        total_tool_errors: 1,
      },
      queries: [
        {
          id: "loop_1",
          question: "Why did revenue change?",
          route: "multi_source_agent",
          tool_call_count: 7,
          round_count: 4,
          tool_error_count: 1,
          thinking_event_count: 9,
          project_name: "Restaurant ops",
        },
      ],
    }),
  },
}));

describe("QueryLoopMetricsDashboard", () => {
  it("renders high-loop query metrics and query rows", async () => {
    render(<QueryLoopMetricsDashboard />);

    await waitFor(() => expect(api.getQueryLoops).toHaveBeenCalled());
    expect(screen.getByText("High-loop queries")).toBeInTheDocument();
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
    expect(screen.getByText("Why did revenue change?")).toBeInTheDocument();
    expect(screen.getByText("multi_source_agent")).toBeInTheDocument();
  });
});
