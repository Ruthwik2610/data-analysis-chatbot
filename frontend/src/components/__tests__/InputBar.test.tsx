import { act, fireEvent, render, screen } from "@testing-library/react";
import { InputBar } from "../InputBar";
import type { Source } from "@/lib/types";

vi.mock("../ConnectorPopover", () => ({
  ConnectorPopover: () => null,
}));

describe("InputBar", () => {
  const selectedSources: Source[] = [
    { id: "s1", name: "pizza_sales.csv", kind: "csv", rows: 48620, active: true },
    { id: "s2", name: "pizza_costs.csv", kind: "csv", rows: 96, active: true },
  ];

  it("submits trimmed text on Enter and clears input", () => {
    const onSend = vi.fn();
    render(
      <InputBar
        onSend={onSend}
        onPickFile={vi.fn()}
        onAttached={vi.fn()}
        disabled={false}
      />,
    );

    const textarea = screen.getByPlaceholderText(
      "Ask about your data, drop a file, or paste a URL…",
    );
    fireEvent.change(textarea, { target: { value: "  top customers  " } });
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter", shiftKey: false });

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("top customers");
    expect((textarea as HTMLTextAreaElement).value).toBe("");
  });

  it("renders stop button when loading and onStop are provided", () => {
    render(
      <InputBar
        onSend={vi.fn()}
        onStop={vi.fn()}
        onPickFile={vi.fn()}
        onAttached={vi.fn()}
        disabled={false}
        loading
      />,
    );
    expect(screen.getByTitle("Stop")).toBeInTheDocument();
  });

  it("renders attach and connect actions in a compact toolbar", () => {
    render(
      <InputBar
        onSend={vi.fn()}
        onPickFile={vi.fn()}
        onAttached={vi.fn()}
        disabled={false}
      />,
    );

    const toolbar = screen.getByRole("toolbar", { name: "Composer actions" });
    expect(toolbar).toBeInTheDocument();
    expect(screen.getByTitle("Attach a file (CSV, Excel, PDF, ZIP/7z, database, JSON)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect" })).toBeInTheDocument();
  });

  it("uses the shared chat content frame for composer alignment", () => {
    render(
      <InputBar
        onSend={vi.fn()}
        onPickFile={vi.fn()}
        onAttached={vi.fn()}
        disabled={false}
      />,
    );

    expect(screen.getByRole("textbox").closest(".chat-content-frame")).not.toBeNull();
  });

  it("lets users choose the query model mode in the composer", () => {
    const onModelModeChange = vi.fn();
    render(
      <InputBar
        onSend={vi.fn()}
        onPickFile={vi.fn()}
        onAttached={vi.fn()}
        disabled={false}
        modelMode="flash"
        onModelModeChange={onModelModeChange}
      />,
    );

    expect(screen.getByRole("option", { name: "Auto" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Query model"), { target: { value: "auto" } });

    expect(onModelModeChange).toHaveBeenCalledWith("auto");
  });

  it("shows selected sources in the composer context row", () => {
    render(
      <InputBar
        onSend={vi.fn()}
        onPickFile={vi.fn()}
        onAttached={vi.fn()}
        disabled={false}
        selectedSources={selectedSources}
      />,
    );

    expect(screen.getAllByText("pizza_sales").length).toBeGreaterThan(0);
    expect(screen.getByText("+1")).toBeInTheDocument();
  });

  it("opens source context details from the selected source chip", () => {
    render(
      <InputBar
        onSend={vi.fn()}
        onPickFile={vi.fn()}
        onAttached={vi.fn()}
        disabled={false}
        selectedSources={selectedSources}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Show selected sources" }));

    expect(screen.getByRole("dialog", { name: "Selected sources" })).toBeInTheDocument();
    expect(screen.getAllByText("pizza_sales").length).toBeGreaterThan(0);
    expect(screen.queryByText("pizza_sales.csv")).not.toBeInTheDocument();
    expect(screen.getByText("48,620 rows")).toBeInTheDocument();
  });

  it("does not submit on Shift+Enter", () => {
    const onSend = vi.fn();
    render(
      <InputBar
        onSend={onSend}
        onPickFile={vi.fn()}
        onAttached={vi.fn()}
        disabled={false}
      />,
    );

    const textarea = screen.getByPlaceholderText(
      "Ask about your data, drop a file, or paste a URL…",
    );
    fireEvent.change(textarea, { target: { value: "top customers" } });
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter", shiftKey: true });

    expect(onSend).not.toHaveBeenCalled();
    expect((textarea as HTMLTextAreaElement).value).toBe("top customers");
  });

  it("keeps voice recognition open and updates from later interim and final results", () => {
    let recognition: any;
    class MockSpeechRecognition {
      continuous = false;
      interimResults = false;
      lang = "";
      onstart: (() => void) | null = null;
      onresult: ((event: any) => void) | null = null;
      onend: (() => void) | null = null;
      start = vi.fn(() => this.onstart?.());
      stop = vi.fn(() => this.onend?.());
      constructor() {
        recognition = this;
      }
    }
    (window as any).SpeechRecognition = MockSpeechRecognition;

    render(
      <InputBar
        onSend={vi.fn()}
        onPickFile={vi.fn()}
        onAttached={vi.fn()}
        disabled={false}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Voice to chat" }));

    expect(recognition.continuous).toBe(true);
    expect(recognition.interimResults).toBe(true);

    act(() => {
      recognition.onresult({
        resultIndex: 0,
        results: [
          { isFinal: true, 0: { transcript: "show revenue " } },
          { isFinal: false, 0: { transcript: "by month" } },
        ],
      });
    });

    const textarea = screen.getByPlaceholderText(
      "Ask about your data, drop a file, or paste a URL…",
    ) as HTMLTextAreaElement;
    expect(textarea.value).toBe("show revenue by month");

    act(() => {
      recognition.onresult({
        resultIndex: 1,
        results: [
          { isFinal: true, 0: { transcript: "show revenue " } },
          { isFinal: true, 0: { transcript: "by month for east" } },
        ],
      });
    });

    expect(textarea.value).toBe("show revenue by month for east");
  });
});
