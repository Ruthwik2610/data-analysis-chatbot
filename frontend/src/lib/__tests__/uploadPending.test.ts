import { buildSheetModeQuestion, buildCustomSheetQuestion } from "../uploadPending";

describe("upload pending helpers", () => {
  it("asks for all sheets or custom sheets before showing sheet checkboxes", () => {
    const pending = buildSheetModeQuestion({
      fileName: "operations.xlsx",
      uploadId: "up_1",
      sheets: ["Orders", "Inventory"],
    });

    expect(pending.content).toContain("Load all sheets or choose specific sheets");
    expect(pending.pending.resolver).toBe("sheet_pick_mode");
    expect(pending.pending.options).toEqual([
      { label: "All sheets", value: "all_sheets" },
      { label: "Custom sheets", value: "custom_sheets" },
    ]);
    expect(pending.pending.args.sheets).toEqual(["Orders", "Inventory"]);
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
