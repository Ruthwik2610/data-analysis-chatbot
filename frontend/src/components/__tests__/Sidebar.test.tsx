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

  it("calls clear screen without deleting the current chat", () => {
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

    fireEvent.click(screen.getByRole("button", { name: "Clear screen" }));

    expect(onNewChat).toHaveBeenCalledTimes(1);
    expect(onDeleteChat).not.toHaveBeenCalled();
  });
});
