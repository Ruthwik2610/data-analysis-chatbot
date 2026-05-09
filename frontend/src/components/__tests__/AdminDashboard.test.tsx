import { render, screen, waitFor } from "@testing-library/react";
import { AdminDashboard } from "../AdminDashboard";
import { api } from "@/lib/api";
import { vi, describe, it, expect } from "vitest";

vi.mock("@/lib/api", () => ({
  api: {
    getAdminStats: vi.fn(),
    getHallucinations: vi.fn(),
  },
}));

describe("AdminDashboard", () => {
  it("renders the high-fidelity insights dashboard with live data", async () => {
    const mockStats = {
      system_metrics: {
        total_chats: 125,
        total_messages: 840,
        avg_query_latency_ms: 120,
        avg_llm_latency_ms: 1800,
        avg_faithfulness: 94.5,
        hallucination_count: 2,
      },
      openrouter: {
        limit: 50,
        usage: 12.45,
        label: "Production Key",
      },
      token_usage_by_project: [
        { project_name: "Sales Analysis", total_tokens: 45000 },
        { project_name: "Inventory", total_tokens: 12000 },
      ],
      top_projects: [{ name: "Sales Analysis", value: 150 }],
      top_sources: [{ name: "orders.csv", value: 85 }],
      config: {
        phoenix_project_name: "test-chatbot"
      }
    };

    const mockHallucinations = [
      {
        id: "h1",
        score: 0.4,
        message_content: "Wrong revenue total",
        reason: "Calculated sum of all rows instead of filtered",
        chat_id: "c1",
        project_name: "Sales Analysis",
        trace_id: "t123"
      }
    ];

    (api.getAdminStats as any).mockResolvedValue(mockStats);
    (api.getHallucinations as any).mockResolvedValue(mockHallucinations);

    render(<AdminDashboard />);

    // Verify loading state
    expect(screen.getByText(/Synthesizing Insights.../i)).toBeInTheDocument();

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText("System Insights")).toBeInTheDocument();
    });

    // Check KPI cards
    expect(screen.getByText("125")).toBeInTheDocument(); // total_chats
    expect(screen.getByText("840")).toBeInTheDocument(); // total_messages
    expect(screen.getByText("120ms")).toBeInTheDocument(); // avg_query_latency
    expect(screen.getByText("1800ms")).toBeInTheDocument(); // avg_llm_latency

    // Check Credit Tracker
    expect(screen.getByText("$12.4500")).toBeInTheDocument();
    expect(screen.getByText(/of \$50.00 monthly quota/)).toBeInTheDocument();

    // Check Hallucination Feed
    expect(screen.getByText("Score: 40%")).toBeInTheDocument();
    expect(screen.getByText(/"Wrong revenue total"/)).toBeInTheDocument();
  });
});
