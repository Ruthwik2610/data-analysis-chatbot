import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    expect(screen.getByTitle("Export result")).toBeInTheDocument();
    expect(screen.getByTitle("Show table")).toBeInTheDocument();
  });

  it("keeps a single structured graph inline even when artifacts are enabled", () => {
    const onOpenArtifact = vi.fn();
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
        onOpenArtifact={onOpenArtifact}
      />,
    );

    expect(screen.getByTitle("Export result")).toBeInTheDocument();
    expect(screen.queryByText(/open side panel/i)).not.toBeInTheDocument();
    expect(onOpenArtifact).not.toHaveBeenCalled();
  });

  it("keeps successful result cards from showing a processing fault", () => {
    const messages: Message[] = [
      {
        id: "a1",
        role: "assistant",
        content: "I couldn't answer that from the available data. The issue was logged for review.",
        error: true,
        result: {
          title: "Total order value by payment mode",
          viz: "bar",
          elapsed_ms: 12,
          sql: "select payment_mode, total_order_val from orders",
          how: "Source: API direct. Model: openrouter/deepseek/deepseek-v4-flash. Metric: sum(total_order_val); grouped by: payment_mode; filters: 0 parameter(s). Display: bar.",
          columns: ["payment_mode", "total_order_val"],
          rows: [["COD", 10200000], ["UPI", 8700000]],
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

    expect(screen.getByText(/Total order value by payment mode/)).toBeInTheDocument();
    expect(screen.queryByText("Processing Fault")).not.toBeInTheDocument();
    expect(screen.queryByText(/Source: API direct/)).not.toBeInTheDocument();
  });

  it("routes multiple structured graphs from one answer to artifacts", () => {
    const onOpenArtifact = vi.fn();
    const messages: Message[] = [
      {
        id: "a1",
        role: "assistant",
        content: "Here are the revenue charts.",
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
        artifacts: [
          {
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
          {
            title: "Revenue by month",
            viz: "line",
            elapsed_ms: 14,
            sql: "select month, revenue from sales",
            how: "Grouped revenue by month.",
            columns: ["month", "revenue"],
            rows: [["2026-05-01", 817860], ["2026-06-01", 912000]],
            row_count: 2,
            truncated: false,
          },
        ],
      },
    ];

    render(
      <MessageList
        messages={messages}
        loading={false}
        onPendingChoice={vi.fn()}
        onPickFile={vi.fn()}
        onConnectClick={vi.fn()}
        onOpenArtifact={onOpenArtifact}
      />,
    );

    expect(screen.queryByTitle("Export result")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /2 artifacts/i }));
    expect(onOpenArtifact).toHaveBeenCalledWith("a1:artifact:0");
  });

  it("keeps the empty-state hero clean so the composer can sit below the heading", () => {
    render(
      <MessageList
        messages={[]}
        loading={false}
        onPendingChoice={vi.fn()}
        onPickFile={vi.fn()}
        onConnectClick={vi.fn()}
      />,
    );

    expect(screen.queryByText("Upload Source")).not.toBeInTheDocument();
    expect(screen.queryByText("Connect context")).not.toBeInTheDocument();
    expect(screen.queryByText(/Enterprise Grade/i)).not.toBeInTheDocument();
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

    expect(screen.getByRole("heading", { name: /The intelligent layer for your business data/i })).toBeInTheDocument();
    expect(screen.getByText(/Connect your CSVs, Databases, or APIs and start chatting/i)).toBeInTheDocument();
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
    expect(screen.getByText("Revenue increased by 12%.").closest(".chat-content-frame")).not.toBeNull();
  });

  it("lets users rerun the previous question without showing debug reporting in chat", () => {
    const onRetryQuestion = vi.fn();
    render(
      <MessageList
        messages={[
          { id: "u1", role: "user", content: "Show revenue by month" },
          { id: "a1", role: "assistant", content: "Revenue peaked in May." },
        ]}
        loading={false}
        onPendingChoice={vi.fn()}
        onPickFile={vi.fn()}
        onConnectClick={vi.fn()}
        onRetryQuestion={onRetryQuestion}
        onFeedback={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Rerun answer" }));

    expect(onRetryQuestion).toHaveBeenCalledWith("Show revenue by month");
    expect(screen.queryByRole("button", { name: "Report answer bug" })).not.toBeInTheDocument();
  });

  it("passes the current chat id to travel itinerary downloads", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: "journey_1", status: "downloaded" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:journey"),
      revokeObjectURL: vi.fn(),
    });

    const messages: Message[] = [
      {
        id: "assistant_msg_1",
        role: "assistant",
        content: "",
        travel_intent: {
          origin: "SFO",
          destination: "JFK",
          departure_date: "2026-06-01",
          return_date: "2026-06-05",
          passengers: 1,
          cabin_class: "economy",
          traveler_tier: "standard",
          budget_limit_usd: 1200,
          check_in_date: null,
          check_out_date: null,
          rooms: 1,
          guests: 1,
          wants_flights: true,
          wants_hotels: false,
        },
        travel_offers: [{
          offer_id: "flight_1",
          airline: "United",
          airline_iata: "UA",
          origin: "SFO",
          destination: "JFK",
          departure_at: "2026-06-01T08:00:00Z",
          arrival_at: "2026-06-01T16:30:00Z",
          duration_minutes: 330,
          stops: 0,
          cabin_class: "economy",
          price_usd: 410,
          currency: "USD",
          policy_compliant: true,
          policy_violation_reason: null,
          booking_redirect_url: "https://book.example.com/flight_1",
          expires_at: null,
          score: 95,
        }],
        hotel_offers: [],
      },
    ];

    render(
      <MessageList
        messages={messages}
        loading={false}
        currentChatId="chat_actual_1"
        onPendingChoice={vi.fn()}
        onPickFile={vi.fn()}
        onConnectClick={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Select outbound flight to JFK" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Download PDF itinerary" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.chat_id).toBe("chat_actual_1");
  });
});
