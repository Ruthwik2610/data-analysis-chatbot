import { fireEvent, render, screen } from "@testing-library/react";
import { Sidebar } from "../Sidebar";
import type { ChatSummary, Project, Source } from "@/lib/types";

const chats: ChatSummary[] = [
  { id: "c1", title: "Pizza margin review", created_at: 1, updated_at: 2, message_count: 4 },
];

const projects: Project[] = [
  { id: "p1", title: "Restaurant ops", created_at: 1, updated_at: 2, files: [] },
];

const sources: Source[] = [
  { id: "s1", name: "pizza_sales.csv", kind: "csv", rows: 48620, active: true },
];

function renderSidebar() {
  render(
    <Sidebar
      chats={chats}
      currentChatId="c1"
      sources={sources}
      selectedSourceIds={["s1"]}
      onNewChat={vi.fn()}
      onSelectChat={vi.fn()}
      onDeleteChat={vi.fn()}
      onToggleSource={vi.fn()}
      onDeleteSource={vi.fn()}
      projects={projects}
      currentProjectId={null}
      onSelectProject={vi.fn()}
      onNewProject={vi.fn()}
      onDeleteProject={vi.fn()}
    />,
  );
}

describe("Sidebar", () => {
  it("places chats, projects, and sources in one premium sidebar", () => {
    renderSidebar();

    expect(screen.queryByRole("tab", { name: "Chats" })).not.toBeInTheDocument();
    expect(screen.getByText("Pizza margin review")).toBeInTheDocument();
    expect(screen.getByText("Restaurant ops")).toBeInTheDocument();
    expect(screen.getByText("pizza_sales")).toBeInTheDocument();
    expect(screen.queryByText("pizza_sales.csv")).not.toBeInTheDocument();
  });

  it("keeps clear screen out of the sidebar", () => {
    const onNewChat = vi.fn();
    const onDeleteChat = vi.fn();
    render(
      <Sidebar
        chats={chats}
        currentChatId="c1"
        sources={sources}
        selectedSourceIds={["s1"]}
        onNewChat={onNewChat}
        onSelectChat={vi.fn()}
        onDeleteChat={onDeleteChat}
        onToggleSource={vi.fn()}
        onDeleteSource={vi.fn()}
        projects={projects}
        currentProjectId={null}
        onSelectProject={vi.fn()}
        onNewProject={vi.fn()}
        onDeleteProject={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Clear screen" })).not.toBeInTheDocument();
    expect(onNewChat).not.toHaveBeenCalled();
    expect(onDeleteChat).not.toHaveBeenCalled();
  });

  it("does not show admin navigation to regular users", () => {
    renderSidebar();

    expect(screen.queryByRole("link", { name: "Admin Control Center" })).not.toBeInTheDocument();
  });

  it("shows admin navigation only when admin access is verified", () => {
    render(
      <Sidebar
        chats={chats}
        currentChatId="c1"
        sources={sources}
        selectedSourceIds={["s1"]}
        onNewChat={vi.fn()}
        onSelectChat={vi.fn()}
        onDeleteChat={vi.fn()}
        onToggleSource={vi.fn()}
        onDeleteSource={vi.fn()}
        projects={projects}
        currentProjectId={null}
        onSelectProject={vi.fn()}
        onNewProject={vi.fn()}
        onDeleteProject={vi.fn()}
        isAdmin
      />,
    );

    expect(screen.getByRole("link", { name: "Admin Control Center" })).toHaveAttribute("href", "/admin");
    expect(screen.getByRole("link", { name: "Debug review inbox" })).toHaveAttribute("href", "/admin/feedback");
  });

  it("groups workbook sheet sources under one removable workbook row", () => {
    const sheetSources: Source[] = Array.from({ length: 9 }, (_, index) => ({
      id: `sheet_${index + 1}`,
      name: `travel_report.xlsx - Sheet ${index + 1}`,
      kind: "xlsx",
      rows: 10 + index,
      active: index === 0,
    }));

    render(
      <Sidebar
        chats={chats}
        currentChatId="c1"
        sources={sheetSources}
        selectedSourceIds={["sheet_1"]}
        onNewChat={vi.fn()}
        onSelectChat={vi.fn()}
        onDeleteChat={vi.fn()}
        onToggleSource={vi.fn()}
        onDeleteSource={vi.fn()}
        projects={projects}
        currentProjectId={null}
        onSelectProject={vi.fn()}
        onNewProject={vi.fn()}
        onDeleteProject={vi.fn()}
      />,
    );

    expect(screen.getByText("travel_report")).toBeInTheDocument();
    expect(screen.queryByText("travel_report.xlsx - Sheet 8")).not.toBeInTheDocument();
    expect(screen.queryByText("travel_report.xlsx - Sheet 9")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete travel_report" })).toBeInTheDocument();
  });
});
