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
});
