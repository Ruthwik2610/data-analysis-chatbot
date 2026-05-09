import { render, screen, waitFor } from "@testing-library/react";
import { ObservabilityDashboard } from "../admin/ObservabilityDashboard";
import { api } from "@/lib/api";
import { vi, describe, it, expect } from "vitest";

vi.mock("@/lib/api", () => ({
  api: {
    getTraces: vi.fn(),
  },
}));

describe("ObservabilityDashboard", () => {
  it("renders live traces and system-wide quality metrics", async () => {
    const mockTraceResponse = {
      traces: [
        {
          id: "msg_1",
          query: "Total revenue for 2024?",
          trace_id: "trace_abc",
          status: "success",
          timestamp: Date.now() / 1000,
          phoenix_url: "https://app.phoenix.arize.com/trace_abc"
        },
        {
          id: "msg_2",
          query: "Explain monthly trends",
          trace_id: "trace_def",
          status: "hallucination",
          timestamp: (Date.now() - 3600000) / 1000,
          phoenix_url: "https://app.phoenix.arize.com/trace_def"
        }
      ],
      config: {
        phoenix_project_name: "custom-bot"
      },
      metrics: {
        avg_faithfulness: 88.2,
        hallucination_count: 5,
        trace_volume: 42
      }
    };

    (api.getTraces as any).mockResolvedValue(mockTraceResponse);

    render(<ObservabilityDashboard />);

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText("Observability")).toBeInTheDocument();
    });

    // Check KPI cards
    expect(screen.getByText("88.2%")).toBeInTheDocument(); // avg_faithfulness
    expect(screen.getByText("5")).toBeInTheDocument(); // hallucination_count
    expect(screen.getByText("42")).toBeInTheDocument(); // trace_volume

    // Check Trace Stream
    expect(screen.getByText("Total revenue for 2024?")).toBeInTheDocument();
    expect(screen.getByText("Explain monthly trends")).toBeInTheDocument();
    
    // Check status badges
    expect(screen.getByText("success")).toBeInTheDocument();
    expect(screen.getByText("hallucination")).toBeInTheDocument();
  });
});
