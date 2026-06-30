import { fireEvent, render, screen } from "@testing-library/react";
import { SettingsPanel } from "./page";

describe("SettingsPanel", () => {
  it("shows a vendor-free business logic switch", () => {
    const onBusinessLogicEnabledChange = vi.fn();

    render(
      <SettingsPanel
        modelMode="auto"
        onModelModeChange={vi.fn()}
        businessLogicEnabled={false}
        onBusinessLogicEnabledChange={onBusinessLogicEnabledChange}
        onClose={vi.fn()}
        onClearChat={vi.fn()}
        isAdmin={false}
      />,
    );

    const toggle = screen.getByRole("switch", { name: "Business Logic Layer" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText("Business Logic Layer")).toBeInTheDocument();
    expect(screen.queryByText(/wren/i)).not.toBeInTheDocument();

    fireEvent.click(toggle);
    expect(onBusinessLogicEnabledChange).toHaveBeenCalledWith(true);
  });
});
