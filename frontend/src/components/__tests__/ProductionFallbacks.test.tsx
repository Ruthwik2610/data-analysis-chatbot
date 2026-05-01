import { render, screen } from "@testing-library/react";
import GlobalError from "@/app/global-error";
import NotFound from "@/app/not-found";

describe("Production fallbacks", () => {
  it("renders a recovery action for uncaught errors", () => {
    render(<GlobalError error={new Error("boom")} reset={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("renders a useful not found state", () => {
    render(<NotFound />);

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to chat" })).toHaveAttribute("href", "/");
  });
});
