import { render, screen } from "@testing-library/react";
import { ThinkingIndicator } from "../ThinkingIndicator";

describe("ThinkingIndicator", () => {
  it("renders step with progress when progress is valid", () => {
    render(<ThinkingIndicator step="Querying source" progress={42} />);
    expect(screen.getByText("Querying source · 42%")).toBeInTheDocument();
  });

  it("renders ellipsis when progress is missing", () => {
    render(<ThinkingIndicator step="Planning" />);
    expect(screen.getByText("Planning…")).toBeInTheDocument();
  });

  it("does not render SQL or internal details from thinking text", () => {
    render(<ThinkingIndicator step="Running SELECT * FROM orders WHERE token = 'secret'" />);

    expect(screen.getByText("Working on your answer…")).toBeInTheDocument();
    expect(screen.queryByText(/select|token|secret/i)).not.toBeInTheDocument();
  });

  it("does not render when step is empty", () => {
    const { container } = render(<ThinkingIndicator step={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
