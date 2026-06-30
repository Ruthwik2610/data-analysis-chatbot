import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AdminLayout from "@/app/admin/layout";
import { api } from "@/lib/api";

let pathname = "/admin";
const replace = vi.fn();
const push = vi.fn();
const router = { replace, push };
const storage: Record<string, string> = {};

vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useRouter: () => router,
}));

vi.mock("@/lib/api", () => ({
  api: {
    getAdminSession: vi.fn(),
  },
  getAuthToken: vi.fn(() => storage.datachat_user_token ?? ""),
}));

describe("AdminLayout", () => {
  beforeEach(() => {
    Object.keys(storage).forEach((key) => delete storage[key]);
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: vi.fn((key: string) => storage[key] ?? null),
        setItem: vi.fn((key: string, value: string) => {
          storage[key] = value;
        }),
        removeItem: vi.fn((key: string) => {
          delete storage[key];
        }),
      },
    });
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: window.localStorage,
    });
    pathname = "/admin";
    replace.mockClear();
    push.mockClear();
    localStorage.removeItem("datachat_admin_token");
    localStorage.removeItem("theme");
    document.documentElement.removeAttribute("data-theme");
    (api.getAdminSession as any).mockClear();
    (api.getAdminSession as any).mockResolvedValue({ ok: true, role: "admin" });
  });

  it("uses theme-aware admin navigation in light mode", async () => {
    localStorage.setItem("datachat_admin_token", "token");

    render(<AdminLayout><div>Admin content</div></AdminLayout>);

    const insights = await screen.findByRole("link", { name: "Insights" });
    expect(insights.className).not.toContain("text-white");
    expect(insights).toHaveStyle({ color: "var(--color-text-primary)" });
  });

  it("provides a top-level dark mode switch in the admin shell", async () => {
    localStorage.setItem("datachat_admin_token", "token");

    render(<AdminLayout><div>Admin content</div></AdminLayout>);

    await waitFor(() => expect(screen.getByText("Admin content")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Switch to dark mode" }));

    expect(localStorage.getItem("theme")).toBe("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(screen.getByRole("button", { name: "Switch to light mode" })).toBeInTheDocument();
  });

  it("allows the admin shell when a test user session is authorized", async () => {
    localStorage.setItem("datachat_user_token", "test-user-token");

    render(<AdminLayout><div>Admin content</div></AdminLayout>);

    await waitFor(() => expect(screen.getByText("Admin content")).toBeInTheDocument());
    expect(api.getAdminSession).toHaveBeenCalledTimes(1);
    expect(replace).not.toHaveBeenCalledWith("/admin/login");
  });
});
