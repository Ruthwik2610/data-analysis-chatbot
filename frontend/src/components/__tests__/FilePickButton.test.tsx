import { fireEvent, render } from "@testing-library/react";
import { FilePickButton } from "../FilePickButton";

describe("FilePickButton", () => {
  it("calls onPick when a file is selected", () => {
    const onPick = vi.fn();
    const { container } = render(<FilePickButton onPick={onPick} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["hello"], "sample.csv", { type: "text/csv" });
    fireEvent.change(input, { target: { files: [file] } });
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick).toHaveBeenCalledWith(file);
  });

  it("does not call onPick when selection is empty", () => {
    const onPick = vi.fn();
    const { container } = render(<FilePickButton onPick={onPick} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [] } });
    expect(onPick).not.toHaveBeenCalled();
  });

  it("accepts PDF, ZIP, and 7z files alongside tabular uploads", () => {
    const { container } = render(<FilePickButton onPick={vi.fn()} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input.accept).toContain(".pdf");
    expect(input.accept).toContain(".zip");
    expect(input.accept).toContain(".7z");
  });
});
