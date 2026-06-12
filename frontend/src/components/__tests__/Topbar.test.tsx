import { fireEvent, render, screen } from "@testing-library/react";
import { Topbar } from "../Topbar";
import type { Source } from "@/lib/types";

const sources: Source[] = [
  { id: "s1", name: "pizza_sales.csv", kind: "csv", rows: 48620, active: true },
  { id: "s2", name: "pizza_costs.csv", kind: "csv", rows: 96, active: true },
  { id: "s3", name: "promo_calendar.xlsx", kind: "xlsx", rows: 12, active: true },
];

describe("Topbar", () => {
  it("shows title and project without duplicating selected source context", () => {
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
    expect(screen.queryByText("pizza_sales")).not.toBeInTheDocument();
    expect(screen.queryByText("+2")).not.toBeInTheDocument();
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

  it("wires settings without exposing admin feedback to regular users", () => {
    const onOpenSettings = vi.fn();
    render(
      <Topbar
        title="Pizza analysis"
        activeSource={sources[0]}
        selectedSources={sources}
        projectName="Restaurant ops"
        onOpenSettings={onOpenSettings}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(onOpenSettings).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("link", { name: "Feedback inbox" })).not.toBeInTheDocument();
    expect(screen.getByTitle("Switch to dark mode")).toHaveAttribute("aria-label", "Switch to dark mode");
    expect(screen.getByText("Pizza analysis").closest(".chat-content-frame")).not.toBeNull();
  });

  it("shows admin feedback navigation only when admin access is verified", () => {
    render(
      <Topbar
        title="Pizza analysis"
        activeSource={sources[0]}
        selectedSources={sources}
        projectName="Restaurant ops"
        isAdmin
      />,
    );

    expect(screen.getByRole("link", { name: "Feedback inbox" })).toHaveAttribute("href", "/admin/feedback");
  });

  it("shows and toggles the artifacts panel control", () => {
    const onToggleArtifacts = vi.fn();
    render(
      <Topbar
        title="Pizza analysis"
        activeSource={sources[0]}
        selectedSources={sources}
        artifactCount={2}
        artifactsOpen
        onToggleArtifacts={onToggleArtifacts}
      />,
    );

    const toggle = screen.getByRole("button", { name: "Toggle artifacts panel" });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("2")).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(onToggleArtifacts).toHaveBeenCalledTimes(1);
  });
});
