import { render, screen } from "@testing-library/react";
import LoginPage from "@/app/admin/login/page";
import { AuthScreen } from "../AuthScreen";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

describe("Login credential hints", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_TEST_USER_EMAIL", "sample-test-user@example.com");
    vi.stubEnv("NEXT_PUBLIC_TEST_USER_PASSWORD", "sample-public-test-password");
    vi.stubEnv("NEXT_PUBLIC_ADMIN_PASSCODE", "sample-public-admin-passcode");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("keeps public test user credentials hidden on the chat login screen", () => {
    render(<AuthScreen onAuthenticated={vi.fn()} />);

    expect(screen.queryByText("Test user")).not.toBeInTheDocument();
    expect(screen.queryByText("sample-test-user@example.com")).not.toBeInTheDocument();
    expect(screen.queryByText("sample-public-test-password")).not.toBeInTheDocument();
  });

  it("shows the admin passcode on the admin login screen", () => {
    render(<LoginPage />);

    expect(screen.getByText("Admin passcode")).toBeInTheDocument();
    expect(screen.getByText("sample-public-admin-passcode")).toBeInTheDocument();
  });

  it("does not show credential panels unless public env vars are configured", () => {
    vi.unstubAllEnvs();

    render(<AuthScreen onAuthenticated={vi.fn()} />);
    expect(screen.queryByText("Test user")).not.toBeInTheDocument();
  });
});
