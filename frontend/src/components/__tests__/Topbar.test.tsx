import { render, screen } from "@testing-library/react";
import { Topbar } from "../Topbar";
import type { Source } from "@/lib/types";

const sources: Source[] = [
  { id: "s1", name: "pizza_sales.csv", kind: "csv", rows: 48620, active: true },
  { id: "s2", name: "pizza_costs.csv", kind: "csv", rows: 96, active: true },
  { id: "s3", name: "promo_calendar.xlsx", kind: "xlsx", rows: 12, active: true },
];

describe("Topbar", () => {
  it("shows the premium search field", () => {
    render(
      <Topbar
        title="Pizza analysis"
        activeSource={sources[0]}
        selectedSources={sources}
        projectName="Restaurant ops"
      />,
    );

    expect(screen.getByPlaceholderText("Search conversations...")).toBeInTheDocument();
  });

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

  it("keeps model controls out of the topbar", () => {
    render(
      <Topbar
        title="Pizza analysis"
        activeSource={sources[0]}
        selectedSources={sources}
        projectName="Restaurant ops"
      />,
    );

    expect(screen.queryByLabelText("Query model")).not.toBeInTheDocument();
  });

  it("constrains long selected source names", () => {
    const longSource: Source = {
      id: "long",
      name: "very_long_enterprise_revenue_extract_for_all_regions_and_channels.csv",
      kind: "csv",
      rows: 1245000,
      active: true,
    };
    render(
      <Topbar
        title="Long source analysis"
        activeSource={longSource}
        selectedSources={[longSource]}
        projectName="Restaurant ops"
      />,
    );

    expect(screen.getByText("very_long_enterprise_revenue_extract_for_all_regions_and_channels")).toHaveClass("truncate");
  });
});
