import { fireEvent, render, screen } from "@testing-library/react";
import { InlineQuestion } from "../InlineQuestion";

describe("InlineQuestion", () => {
  it("submits a custom clarification answer", () => {
    const onChoose = vi.fn();
    render(
      <InlineQuestion
        label="Which metric should I use?"
        options={[]}
        onChoose={onChoose}
        allowCustom
      />,
    );

    fireEvent.change(screen.getByLabelText("Clarification answer"), {
      target: { value: "Use net revenue by month" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send clarification" }));

    expect(onChoose).toHaveBeenCalledWith("Use net revenue by month");
  });

  it("lets users select several Excel sheets before submitting", () => {
    const onChoose = vi.fn();
    render(
      <InlineQuestion
        label="Pick sheets"
        options={[
          { label: "Orders", value: "Orders" },
          { label: "Inventory", value: "Inventory" },
          { label: "Ignored", value: "Ignored" },
        ]}
        onChoose={onChoose}
        multiSelect
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Orders" }));
    fireEvent.click(screen.getByRole("button", { name: "Inventory" }));
    fireEvent.click(screen.getByRole("button", { name: "Load 2 sheets" }));

    expect(onChoose).toHaveBeenCalledWith(["Orders", "Inventory"]);
  });
});
