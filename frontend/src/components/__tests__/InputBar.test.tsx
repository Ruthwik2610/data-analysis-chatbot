import { fireEvent, render, screen } from "@testing-library/react";
import { InputBar } from "../InputBar";

vi.mock("../ConnectorPopover", () => ({
  ConnectorPopover: () => null,
}));

describe("InputBar", () => {
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
    expect(screen.getByTitle("Attach a file (CSV, Excel, database, JSON)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect" })).toBeInTheDocument();
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
});
