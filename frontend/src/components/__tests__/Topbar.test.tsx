import { render, screen } from "@testing-library/react";
import { Topbar } from "../Topbar";
import type { Source } from "@/lib/types";

const sources: Source[] = [
  { id: "s1", name: "pizza_sales.csv", kind: "csv", rows: 48620, active: true },
  { id: "s2", name: "pizza_costs.csv", kind: "csv", rows: 96, active: true },
  { id: "s3", name: "promo_calendar.xlsx", kind: "xlsx", rows: 12, active: true },
];

describe("Topbar", () => {
  it("shows title, project, first selected source, and overflow count", () => {
    render(
      <Topbar
        title="Pizza analysis"
        activeSource={sources[0]}
        selectedSources={sources}
        projectName="Restaurant ops"
      />,
    );

    expect(screen.getByText("Pizza analysis")).toBeInTheDocument();
    expect(screen.getByText("Restaurant ops")).toBeInTheDocument();
    expect(screen.getByText("pizza_sales")).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
  });
});
