import { displaySourceName } from "../displayNames";

describe("displaySourceName", () => {
  it("hides common file extensions from source names", () => {
    expect(displaySourceName("Orders.xlsx")).toBe("Orders");
    expect(displaySourceName("pizza_sales.csv")).toBe("pizza_sales");
    expect(displaySourceName("Sales Book Report.PDF")).toBe("Sales Book Report");
  });

  it("keeps non-file source names intact", () => {
    expect(displaySourceName("BigQuery Warehouse")).toBe("BigQuery Warehouse");
    expect(displaySourceName("orders.backup.final.csv")).toBe("orders.backup.final");
  });
});
