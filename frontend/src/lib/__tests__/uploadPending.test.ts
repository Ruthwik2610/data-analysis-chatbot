import { buildSheetModeQuestion, buildCustomSheetQuestion } from "../uploadPending";

describe("upload pending helpers", () => {
  it("asks the user to pick a single sheet to open as the source", () => {
    const pending = buildSheetModeQuestion({
      fileName: "operations.xlsx",
      uploadId: "up_1",
      sheets: ["Orders", "Inventory"],
    });

    expect(pending.content).toContain("which one should I open");
    expect(pending.pending.resolver).toBe("sheet_pick");
    expect(pending.pending.multiSelect).toBeFalsy();
    expect(pending.pending.options).toEqual([
      { label: "Orders", value: "Orders" },
      { label: "Inventory", value: "Inventory" },
    ]);
  });

  it("turns custom sheet mode into a multi-select sheet picker", () => {
    const pending = buildCustomSheetQuestion({
      fileName: "operations.xlsx",
      uploadId: "up_1",
      sheets: ["Orders", "Inventory"],
    });

    expect(pending.pending.resolver).toBe("sheet_pick");
    expect(pending.pending.multiSelect).toBe(true);
    expect(pending.pending.options).toEqual([
      { label: "Orders", value: "Orders" },
      { label: "Inventory", value: "Inventory" },
    ]);
  });
});
